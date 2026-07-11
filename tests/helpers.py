import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from ops_evidence_api.application.errors import IdempotencyConflictError, IncidentNotFoundError
from ops_evidence_api.application.models import (
    Analysis,
    AnalysisStatus,
    CreateIncidentCommand,
    Incident,
    StartAnalysisCommand,
    StartAnalysisResult,
)

ROOT = Path(__file__).resolve().parents[1]


def load_fixture_payload(scenario: str = "db-pool-exhaustion") -> dict[str, object]:
    fixture_dir = ROOT / "fixtures" / scenario
    payload = json.loads((fixture_dir / "incident.json").read_text(encoding="utf-8"))
    payload["logs"] = {
        "format": "jsonl",
        "content": (fixture_dir / "logs.jsonl").read_text(encoding="utf-8"),
    }
    payload["runbook"] = {
        "id": "runbook:db-pool-saturation",
        "title": "Database connection pool saturation",
        "content": (fixture_dir / "runbook.md").read_text(encoding="utf-8"),
    }
    return payload


class MemoryEvidenceStore:
    def __init__(self) -> None:
        self.incidents: dict[UUID, Incident] = {}
        self.analyses: dict[UUID, Analysis] = {}
        self.keys: dict[str, tuple[str, UUID]] = {}
        self.last_start_command: StartAnalysisCommand | None = None

    async def create_incident(self, command: CreateIncidentCommand) -> Incident:
        incident = Incident(
            id=uuid4(),
            title=command.title,
            scenario_id=command.scenario_id,
            alert=command.alert,
            logs=command.logs,
            runbook=command.runbook,
            created_at=datetime.now(UTC),
        )
        self.incidents[incident.id] = incident
        return incident

    async def get_incident(self, incident_id: UUID) -> Incident | None:
        return self.incidents.get(incident_id)

    async def start_analysis(self, command: StartAnalysisCommand) -> StartAnalysisResult:
        if command.incident_id not in self.incidents:
            raise IncidentNotFoundError(command.incident_id)
        self.last_start_command = command
        existing = self.keys.get(command.idempotency_key)
        if existing is not None:
            fingerprint, analysis_id = existing
            if fingerprint != command.request_fingerprint:
                raise IdempotencyConflictError(command.idempotency_key)
            return StartAnalysisResult(self.analyses[analysis_id], replayed=True)

        analysis = Analysis(
            id=command.analysis_id,
            incident_id=command.incident_id,
            status=AnalysisStatus.QUEUED,
            result=None,
            failure=None,
            created_at=command.created_at,
            updated_at=command.created_at,
        )
        self.analyses[analysis.id] = analysis
        self.keys[command.idempotency_key] = (command.request_fingerprint, analysis.id)
        return StartAnalysisResult(analysis, replayed=False)

    async def get_analysis(self, analysis_id: UUID) -> Analysis | None:
        return self.analyses.get(analysis_id)
