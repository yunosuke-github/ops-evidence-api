from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from ops_evidence_api.contracts.api import AnalysisFailure, AnalysisResult
from ops_evidence_api.contracts.common import ContractModel


class EventContract(ContractModel):
    event_id: UUID
    schema_version: Literal["1.0"] = "1.0"
    occurred_at: AwareDatetime
    analysis_id: UUID
    correlation_id: UUID
    traceparent: Annotated[str | None, Field(default=None, max_length=255)]


class AnalysisRequestedEvent(EventContract):
    event_type: Literal["analysis.requested"] = "analysis.requested"
    incident_id: UUID
    input_uri: Annotated[str, Field(pattern=r"^/internal/v1/analyses/.+/input$")]
    scenario_id: str | None = None


class AnalysisProgressedEvent(EventContract):
    event_type: Literal["analysis.progressed"] = "analysis.progressed"
    stage: Literal["retrieving", "analyzing", "validating"]
    sequence: Annotated[int, Field(ge=1)]


class AnalysisCompletedEvent(EventContract):
    event_type: Literal["analysis.completed"] = "analysis.completed"
    result: AnalysisResult


class AnalysisFailedEvent(EventContract):
    event_type: Literal["analysis.failed"] = "analysis.failed"
    failure: AnalysisFailure
