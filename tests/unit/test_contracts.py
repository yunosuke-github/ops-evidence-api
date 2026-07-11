from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ops_evidence_api.application.models import AnalysisStatus
from ops_evidence_api.contracts.api import AnalysisFailure, AnalysisResponse, AnalysisResult
from tests.helpers import ROOT


def load_expected_result() -> AnalysisResult:
    path = ROOT / "fixtures/db-pool-exhaustion/expected-analysis.json"
    return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))


def test_expected_result_has_only_resolvable_references() -> None:
    result = load_expected_result()

    assert result.hypotheses[0].evidence_score == 88
    assert result.metadata.deterministic is True


def test_unknown_evidence_reference_is_rejected() -> None:
    result = load_expected_result().model_dump(mode="json", by_alias=True)
    result["timeline"][0]["evidenceIds"] = ["log:missing"]

    with pytest.raises(ValidationError, match="Unknown evidence references"):
        AnalysisResult.model_validate(result)


def test_completed_analysis_requires_a_result() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError, match="must include a result"):
        AnalysisResponse(
            id=uuid4(),
            incident_id=uuid4(),
            status=AnalysisStatus.COMPLETED,
            created_at=now,
            updated_at=now,
        )


def test_terminal_states_cannot_contain_both_result_and_failure() -> None:
    now = datetime.now(UTC)
    result = load_expected_result()
    failure = AnalysisFailure(code="MODEL_FAILED", detail="Synthetic failure.", retryable=False)

    with pytest.raises(ValidationError, match="cannot include failure"):
        AnalysisResponse(
            id=uuid4(),
            incident_id=uuid4(),
            status=AnalysisStatus.COMPLETED,
            result=result,
            failure=failure,
            created_at=now,
            updated_at=now,
        )
    with pytest.raises(ValidationError, match="cannot include a result"):
        AnalysisResponse(
            id=uuid4(),
            incident_id=uuid4(),
            status=AnalysisStatus.FAILED,
            result=result,
            failure=failure,
            created_at=now,
            updated_at=now,
        )


def test_non_terminal_state_cannot_contain_a_result() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError, match="non-terminal"):
        AnalysisResponse(
            id=uuid4(),
            incident_id=uuid4(),
            status=AnalysisStatus.ANALYZING,
            result=load_expected_result(),
            created_at=now,
            updated_at=now,
        )
