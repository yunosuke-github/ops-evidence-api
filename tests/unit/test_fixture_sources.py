import json
import re

from ops_evidence_api.contracts.api import AnalysisResult
from tests.helpers import ROOT


def test_expected_evidence_exists_in_the_source_fixture() -> None:
    fixture_dir = ROOT / "fixtures/db-pool-exhaustion"
    incident = json.loads((fixture_dir / "incident.json").read_text(encoding="utf-8"))
    log_ids = {
        json.loads(line)["id"]
        for line in (fixture_dir / "logs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    }
    runbook_ids = set(
        re.findall(
            r"Evidence ID: `([^`]+)`",
            (fixture_dir / "runbook.md").read_text(encoding="utf-8"),
        )
    )
    source_ids = {incident["alert"]["id"], *log_ids, *runbook_ids}
    result = AnalysisResult.model_validate_json(
        (fixture_dir / "expected-analysis.json").read_text(encoding="utf-8")
    )

    assert {evidence.id for evidence in result.evidence} <= source_ids
