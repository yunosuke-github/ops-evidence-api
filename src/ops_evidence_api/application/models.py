from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CreateIncidentCommand:
    title: str
    scenario_id: str | None
    alert: dict[str, Any]
    logs: dict[str, Any]
    runbook: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Incident:
    id: UUID
    title: str
    scenario_id: str | None
    alert: dict[str, Any]
    logs: dict[str, Any]
    runbook: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StartAnalysisCommand:
    analysis_id: UUID
    incident_id: UUID
    idempotency_key: str
    request_fingerprint: str
    outbox_event_id: UUID
    outbox_payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Analysis:
    id: UUID
    incident_id: UUID
    status: AnalysisStatus
    result: dict[str, Any] | None
    failure: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StartAnalysisResult:
    analysis: Analysis
    replayed: bool


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    event_id: UUID
    analysis_id: UUID
    payload: dict[str, Any]
    attempt_count: int
