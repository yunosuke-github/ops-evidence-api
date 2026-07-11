from typing import Protocol
from uuid import UUID

from ops_evidence_api.application.models import (
    Analysis,
    CreateIncidentCommand,
    Incident,
    OutboxMessage,
    StartAnalysisCommand,
    StartAnalysisResult,
)


class EvidenceStore(Protocol):
    async def create_incident(self, command: CreateIncidentCommand) -> Incident: ...

    async def get_incident(self, incident_id: UUID) -> Incident | None: ...

    async def start_analysis(self, command: StartAnalysisCommand) -> StartAnalysisResult: ...

    async def get_analysis(self, analysis_id: UUID) -> Analysis | None: ...


class FakeRunnerStore(Protocol):
    async def claim_next_fake_message(self) -> OutboxMessage | None: ...

    async def complete_fake_message(
        self,
        message: OutboxMessage,
        result: dict[str, object],
    ) -> None: ...

    async def fail_fake_message(
        self,
        message: OutboxMessage,
        *,
        code: str,
        detail: str,
        retryable: bool,
    ) -> None: ...
