from uuid import uuid4

import pytest

from ops_evidence_api.application.models import OutboxMessage
from ops_evidence_api.infrastructure.fake_runner import FakeRunnerError, FixtureAnalysisRunner
from tests.helpers import ROOT


def message_for(scenario_id: str | None) -> OutboxMessage:
    return OutboxMessage(
        event_id=uuid4(),
        analysis_id=uuid4(),
        payload={"scenarioId": scenario_id},
        attempt_count=1,
    )


async def test_fixture_runner_returns_a_valid_deterministic_result() -> None:
    runner = FixtureAnalysisRunner(ROOT / "fixtures")

    result = await runner.run(message_for("db-pool-exhaustion"))

    assert result["metadata"]["deterministic"] is True
    assert result["hypotheses"][0]["evidenceScore"] == 88


@pytest.mark.parametrize("scenario_id", [None, "", "unknown-scenario"])
async def test_fixture_runner_rejects_unknown_scenarios(scenario_id: str | None) -> None:
    runner = FixtureAnalysisRunner(ROOT / "fixtures")

    with pytest.raises(FakeRunnerError) as captured:
        await runner.run(message_for(scenario_id))

    assert captured.value.code == "UNSUPPORTED_SCENARIO"
    assert captured.value.retryable is False
