from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ops_evidence_api.application.errors import (
    IdempotencyConflictError,
    IncidentNotFoundError,
)
from ops_evidence_api.application.models import (
    Analysis,
    AnalysisStatus,
    CreateIncidentCommand,
    Incident,
    OutboxMessage,
    StartAnalysisCommand,
    StartAnalysisResult,
)
from ops_evidence_api.infrastructure.models import (
    AnalysisRecord,
    IncidentRecord,
    OutboxEventRecord,
)

MAX_FAKE_ATTEMPTS = 3


class PostgresEvidenceStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_incident(self, command: CreateIncidentCommand) -> Incident:
        record = IncidentRecord(
            id=uuid4(),
            title=command.title,
            scenario_id=command.scenario_id,
            alert=command.alert,
            logs=command.logs,
            runbook=command.runbook,
            created_at=datetime.now(UTC),
        )
        async with self._session_factory() as session, session.begin():
            session.add(record)
        return self._incident_from_record(record)

    async def get_incident(self, incident_id: UUID) -> Incident | None:
        async with self._session_factory() as session:
            record = await session.get(IncidentRecord, incident_id)
        return self._incident_from_record(record) if record is not None else None

    async def start_analysis(self, command: StartAnalysisCommand) -> StartAnalysisResult:
        try:
            return await self._start_analysis_once(command)
        except IntegrityError as exc:
            # Concurrent requests can both observe no existing key. PostgreSQL resolves the
            # unique-key race; this second read returns the committed winner.
            diagnostic = getattr(exc.orig, "diag", None)
            if getattr(diagnostic, "constraint_name", None) != "uq_analyses_idempotency_key":
                raise
            existing = await self._get_analysis_by_idempotency_key(command.idempotency_key)
            if existing is None:
                raise
            return self._resolve_idempotent_replay(existing, command)

    async def _start_analysis_once(
        self,
        command: StartAnalysisCommand,
    ) -> StartAnalysisResult:
        async with self._session_factory() as session, session.begin():
            incident = await session.get(IncidentRecord, command.incident_id)
            if incident is None:
                raise IncidentNotFoundError(command.incident_id)

            existing = await session.scalar(
                select(AnalysisRecord).where(
                    AnalysisRecord.idempotency_key == command.idempotency_key
                )
            )
            if existing is not None:
                return self._resolve_idempotent_replay(existing, command)

            analysis = AnalysisRecord(
                id=command.analysis_id,
                incident_id=command.incident_id,
                status=AnalysisStatus.QUEUED.value,
                result=None,
                failure=None,
                idempotency_key=command.idempotency_key,
                request_fingerprint=command.request_fingerprint,
                created_at=command.created_at,
                updated_at=command.created_at,
            )
            outbox_event = OutboxEventRecord(
                event_id=command.outbox_event_id,
                event_type="analysis.requested",
                analysis_id=command.analysis_id,
                payload=command.outbox_payload,
                occurred_at=command.created_at,
                available_at=command.created_at,
                published_at=None,
                attempt_count=0,
                last_error=None,
            )
            session.add_all([analysis, outbox_event])
            await session.flush()
            result = self._analysis_from_record(analysis)
        return StartAnalysisResult(analysis=result, replayed=False)

    async def _get_analysis_by_idempotency_key(self, key: str) -> AnalysisRecord | None:
        async with self._session_factory() as session:
            record: AnalysisRecord | None = await session.scalar(
                select(AnalysisRecord).where(AnalysisRecord.idempotency_key == key)
            )
        return record

    def _resolve_idempotent_replay(
        self,
        existing: AnalysisRecord,
        command: StartAnalysisCommand,
    ) -> StartAnalysisResult:
        if existing.request_fingerprint != command.request_fingerprint:
            raise IdempotencyConflictError(command.idempotency_key)
        return StartAnalysisResult(
            analysis=self._analysis_from_record(existing),
            replayed=True,
        )

    async def get_analysis(self, analysis_id: UUID) -> Analysis | None:
        async with self._session_factory() as session:
            record = await session.get(AnalysisRecord, analysis_id)
        return self._analysis_from_record(record) if record is not None else None

    async def claim_next_fake_message(self) -> OutboxMessage | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            event = await session.scalar(
                select(OutboxEventRecord)
                .where(
                    OutboxEventRecord.event_type == "analysis.requested",
                    OutboxEventRecord.published_at.is_(None),
                    OutboxEventRecord.available_at <= now,
                )
                .order_by(OutboxEventRecord.occurred_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if event is None:
                return None

            analysis = await session.get(AnalysisRecord, event.analysis_id)
            if analysis is None:
                event.published_at = now
                event.last_error = "ANALYSIS_NOT_FOUND"
                return None
            if analysis.status in {AnalysisStatus.COMPLETED.value, AnalysisStatus.FAILED.value}:
                event.published_at = now
                return None

            event.attempt_count += 1
            analysis.status = AnalysisStatus.ANALYZING.value
            analysis.updated_at = now
            message = OutboxMessage(
                event_id=event.event_id,
                analysis_id=event.analysis_id,
                payload=dict(event.payload),
                attempt_count=event.attempt_count,
            )
        return message

    async def complete_fake_message(
        self,
        message: OutboxMessage,
        result: dict[str, object],
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            event = await session.get(OutboxEventRecord, message.event_id, with_for_update=True)
            analysis = await session.get(AnalysisRecord, message.analysis_id, with_for_update=True)
            if event is None or analysis is None or event.published_at is not None:
                return
            analysis.status = AnalysisStatus.COMPLETED.value
            analysis.result = result
            analysis.failure = None
            analysis.updated_at = now
            event.published_at = now
            event.last_error = None

    async def fail_fake_message(
        self,
        message: OutboxMessage,
        *,
        code: str,
        detail: str,
        retryable: bool,
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            event = await session.get(OutboxEventRecord, message.event_id, with_for_update=True)
            analysis = await session.get(AnalysisRecord, message.analysis_id, with_for_update=True)
            if event is None or analysis is None or event.published_at is not None:
                return

            event.last_error = f"{code}: {detail}"[:2_000]
            if retryable and message.attempt_count < MAX_FAKE_ATTEMPTS:
                event.available_at = now + timedelta(seconds=2 ** (message.attempt_count - 1))
                analysis.status = AnalysisStatus.QUEUED.value
                analysis.updated_at = now
                return

            analysis.status = AnalysisStatus.FAILED.value
            analysis.failure = {"code": code, "detail": detail, "retryable": retryable}
            analysis.updated_at = now
            event.published_at = now

    @staticmethod
    def _incident_from_record(record: IncidentRecord) -> Incident:
        return Incident(
            id=record.id,
            title=record.title,
            scenario_id=record.scenario_id,
            alert=dict(record.alert),
            logs=dict(record.logs),
            runbook=dict(record.runbook),
            created_at=record.created_at,
        )

    @staticmethod
    def _analysis_from_record(record: AnalysisRecord) -> Analysis:
        return Analysis(
            id=record.id,
            incident_id=record.incident_id,
            status=AnalysisStatus(record.status),
            result=dict(record.result) if record.result is not None else None,
            failure=dict(record.failure) if record.failure is not None else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
