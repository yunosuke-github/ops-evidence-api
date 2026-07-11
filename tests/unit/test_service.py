from uuid import uuid4

import pytest

from ops_evidence_api.application.errors import (
    AnalysisNotFoundError,
    IdempotencyConflictError,
    IncidentNotFoundError,
)
from ops_evidence_api.application.models import CreateIncidentCommand
from ops_evidence_api.application.service import IncidentService
from tests.helpers import MemoryEvidenceStore


def incident_command(title: str = "Synthetic incident") -> CreateIncidentCommand:
    return CreateIncidentCommand(
        title=title,
        scenario_id="db-pool-exhaustion",
        alert={"id": "alert:db-pool-saturation"},
        logs={"format": "text", "content": "synthetic"},
        runbook={"id": "runbook:db-pool-saturation", "content": "synthetic"},
    )


async def test_start_analysis_creates_a_versioned_requested_event() -> None:
    store = MemoryEvidenceStore()
    service = IncidentService(store)
    incident = await service.create_incident(incident_command())

    result = await service.start_analysis(
        incident.id,
        idempotency_key="analysis-key-001",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )

    assert result.replayed is False
    assert store.last_start_command is not None
    event = store.last_start_command.outbox_payload
    assert event["eventType"] == "analysis.requested"
    assert event["schemaVersion"] == "1.0"
    assert event["analysisId"] == str(result.analysis.id)
    assert event["incidentId"] == str(incident.id)
    assert event["scenarioId"] == "db-pool-exhaustion"


async def test_same_idempotency_key_replays_the_original_analysis() -> None:
    store = MemoryEvidenceStore()
    service = IncidentService(store)
    incident = await service.create_incident(incident_command())

    first = await service.start_analysis(
        incident.id,
        idempotency_key="analysis-key-002",
        traceparent=None,
    )
    replay = await service.start_analysis(
        incident.id,
        idempotency_key="analysis-key-002",
        traceparent=None,
    )

    assert replay.replayed is True
    assert replay.analysis.id == first.analysis.id


async def test_idempotency_key_cannot_be_reused_for_another_incident() -> None:
    store = MemoryEvidenceStore()
    service = IncidentService(store)
    first_incident = await service.create_incident(incident_command("First"))
    second_incident = await service.create_incident(incident_command("Second"))
    await service.start_analysis(
        first_incident.id,
        idempotency_key="shared-analysis-key",
        traceparent=None,
    )

    with pytest.raises(IdempotencyConflictError):
        await service.start_analysis(
            second_incident.id,
            idempotency_key="shared-analysis-key",
            traceparent=None,
        )


async def test_missing_resources_raise_typed_errors() -> None:
    service = IncidentService(MemoryEvidenceStore())

    with pytest.raises(IncidentNotFoundError):
        await service.get_incident(uuid4())
    with pytest.raises(IncidentNotFoundError):
        await service.start_analysis(
            uuid4(),
            idempotency_key="missing-incident",
            traceparent=None,
        )
    with pytest.raises(AnalysisNotFoundError):
        await service.get_analysis(uuid4())
