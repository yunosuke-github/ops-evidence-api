import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ops_evidence_api.application.errors import AnalysisNotFoundError, IncidentNotFoundError
from ops_evidence_api.application.models import (
    Analysis,
    CreateIncidentCommand,
    Incident,
    StartAnalysisCommand,
    StartAnalysisResult,
)
from ops_evidence_api.application.ports import EvidenceStore
from ops_evidence_api.contracts.events import AnalysisRequestedEvent


class IncidentService:
    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    async def create_incident(self, command: CreateIncidentCommand) -> Incident:
        return await self._store.create_incident(command)

    async def get_incident(self, incident_id: UUID) -> Incident:
        incident = await self._store.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        return incident

    async def start_analysis(
        self,
        incident_id: UUID,
        *,
        idempotency_key: str,
        traceparent: str | None,
    ) -> StartAnalysisResult:
        incident = await self._store.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)

        created_at = datetime.now(UTC)
        analysis_id = uuid4()
        event = AnalysisRequestedEvent(
            event_id=uuid4(),
            occurred_at=created_at,
            analysis_id=analysis_id,
            incident_id=incident.id,
            correlation_id=analysis_id,
            traceparent=traceparent,
            input_uri=f"/internal/v1/analyses/{analysis_id}/input",
            scenario_id=incident.scenario_id,
        )
        fingerprint = hashlib.sha256(f"v1:{incident_id}".encode()).hexdigest()
        command = StartAnalysisCommand(
            analysis_id=analysis_id,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            outbox_event_id=event.event_id,
            outbox_payload=event.model_dump(mode="json", by_alias=True),
            created_at=created_at,
        )
        return await self._store.start_analysis(command)

    async def get_analysis(self, analysis_id: UUID) -> Analysis:
        analysis = await self._store.get_analysis(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(analysis_id)
        return analysis
