import json

from scripts.export_contracts import build_contracts


def test_generated_contracts_match_checked_in_snapshots() -> None:
    for path, generated in build_contracts().items():
        assert path.exists(), f"Missing generated contract: {path}"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == generated, f"Contract drift detected: {path}"
