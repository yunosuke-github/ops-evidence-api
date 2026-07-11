from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from ops_evidence_api.application.models import AnalysisStatus
from ops_evidence_api.contracts.common import ContractModel

EvidenceId = Annotated[
    str, Field(min_length=3, max_length=120, pattern=r"^[a-z]+:[A-Za-z0-9._-]+$")
]


class AlertInput(ContractModel):
    id: EvidenceId
    name: Annotated[str, Field(min_length=1, max_length=160)]
    source: Annotated[str, Field(min_length=1, max_length=80)]
    fired_at: AwareDatetime
    description: Annotated[str, Field(min_length=1, max_length=2_000)]


class LogsInput(ContractModel):
    format: Literal["jsonl", "text"]
    content: Annotated[str, Field(min_length=1, max_length=128_000)]


class RunbookInput(ContractModel):
    id: EvidenceId
    title: Annotated[str, Field(min_length=1, max_length=160)]
    content: Annotated[str, Field(min_length=1, max_length=64_000)]


class IncidentCreate(ContractModel):
    title: Annotated[str, Field(min_length=1, max_length=160)]
    scenario_id: Annotated[
        str | None,
        Field(default=None, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    ]
    alert: AlertInput
    logs: LogsInput
    runbook: RunbookInput


class IncidentResponse(ContractModel):
    id: UUID
    title: str
    scenario_id: str | None
    created_at: datetime


class EvidenceItem(ContractModel):
    id: EvidenceId
    source_type: Literal["alert", "log", "runbook"]
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    excerpt: Annotated[str, Field(min_length=1, max_length=1_000)]


class TimelineEntry(ContractModel):
    timestamp: AwareDatetime
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    evidence_ids: Annotated[list[EvidenceId], Field(min_length=1)]


class Observation(ContractModel):
    id: Annotated[str, Field(pattern=r"^observation:[A-Za-z0-9._-]+$")]
    statement: Annotated[str, Field(min_length=1, max_length=1_000)]
    evidence_ids: Annotated[list[EvidenceId], Field(min_length=1)]


class Hypothesis(ContractModel):
    id: Annotated[str, Field(pattern=r"^hypothesis:[A-Za-z0-9._-]+$")]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    summary: Annotated[str, Field(min_length=1, max_length=1_500)]
    evidence_score: Annotated[int, Field(ge=0, le=100)]
    supporting_evidence_ids: Annotated[list[EvidenceId], Field(min_length=1)]
    contradicting_evidence_ids: list[EvidenceId] = Field(default_factory=list)


class InformationGap(ContractModel):
    id: Annotated[str, Field(pattern=r"^gap:[A-Za-z0-9._-]+$")]
    description: Annotated[str, Field(min_length=1, max_length=1_000)]


class NextCheck(ContractModel):
    id: Annotated[str, Field(pattern=r"^check:[A-Za-z0-9._-]+$")]
    description: Annotated[str, Field(min_length=1, max_length=1_000)]
    hypothesis_ids: Annotated[list[str], Field(min_length=1)]


class AnalysisMetadata(ContractModel):
    provider: Annotated[str, Field(min_length=1, max_length=80)]
    model: Annotated[str, Field(min_length=1, max_length=120)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=40)]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    latency_ms: Annotated[int, Field(ge=0)]
    deterministic: bool = False


class AnalysisResult(ContractModel):
    evidence: Annotated[list[EvidenceItem], Field(min_length=1)]
    timeline: list[TimelineEntry]
    observations: list[Observation]
    hypotheses: Annotated[list[Hypothesis], Field(min_length=1)]
    information_gaps: list[InformationGap]
    next_checks: list[NextCheck]
    metadata: AnalysisMetadata

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique.")

        known = set(evidence_ids)
        referenced: set[str] = set()
        for entry in self.timeline:
            referenced.update(entry.evidence_ids)
        for observation in self.observations:
            referenced.update(observation.evidence_ids)
        for hypothesis in self.hypotheses:
            referenced.update(hypothesis.supporting_evidence_ids)
            referenced.update(hypothesis.contradicting_evidence_ids)

        unknown = sorted(referenced - known)
        if unknown:
            raise ValueError(f"Unknown evidence references: {', '.join(unknown)}")

        known_hypotheses = {hypothesis.id for hypothesis in self.hypotheses}
        if len(known_hypotheses) != len(self.hypotheses):
            raise ValueError("Hypothesis IDs must be unique.")
        check_references = {
            hypothesis_id
            for next_check in self.next_checks
            for hypothesis_id in next_check.hypothesis_ids
        }
        unknown_hypotheses = sorted(check_references - known_hypotheses)
        if unknown_hypotheses:
            raise ValueError(f"Unknown hypothesis references: {', '.join(unknown_hypotheses)}")
        return self


class AnalysisFailure(ContractModel):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=80)]
    detail: Annotated[str, Field(min_length=1, max_length=1_000)]
    retryable: bool


class AnalysisResponse(ContractModel):
    id: UUID
    incident_id: UUID
    status: AnalysisStatus
    result: AnalysisResult | None = None
    failure: AnalysisFailure | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.status == AnalysisStatus.COMPLETED:
            if self.result is None:
                raise ValueError("A completed analysis must include a result.")
            if self.failure is not None:
                raise ValueError("A completed analysis cannot include failure details.")
        if self.status == AnalysisStatus.FAILED:
            if self.failure is None:
                raise ValueError("A failed analysis must include failure details.")
            if self.result is not None:
                raise ValueError("A failed analysis cannot include a result.")
        if self.status not in {AnalysisStatus.COMPLETED, AnalysisStatus.FAILED}:
            if self.result is not None or self.failure is not None:
                raise ValueError("A non-terminal analysis cannot include a result or failure.")
        return self


class InvalidParameter(ContractModel):
    name: str
    reason: str


class ProblemDetails(ContractModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    errors: list[InvalidParameter] = Field(default_factory=list)


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
