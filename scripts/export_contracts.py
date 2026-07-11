import json
from pathlib import Path
from typing import Any

from ops_evidence_api.contracts.api import AnalysisResult
from ops_evidence_api.contracts.common import ContractModel
from ops_evidence_api.contracts.events import (
    AnalysisCompletedEvent,
    AnalysisFailedEvent,
    AnalysisProgressedEvent,
    AnalysisRequestedEvent,
)
from ops_evidence_api.main import app

ROOT = Path(__file__).resolve().parents[1]


def build_contracts() -> dict[Path, dict[str, Any]]:
    event_models: dict[str, type[ContractModel]] = {
        "analysis-requested.schema.json": AnalysisRequestedEvent,
        "analysis-progressed.schema.json": AnalysisProgressedEvent,
        "analysis-completed.schema.json": AnalysisCompletedEvent,
        "analysis-failed.schema.json": AnalysisFailedEvent,
    }
    result_schema = AnalysisResult.model_json_schema(by_alias=True)
    result_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    result_schema["$id"] = (
        "https://ynaito.dev/schemas/ops-evidence/results/v1/analysis-result.schema.json"
    )
    contracts: dict[Path, dict[str, Any]] = {
        ROOT / "contracts/http/openapi.json": app.openapi(),
        ROOT / "contracts/results/v1/analysis-result.schema.json": result_schema,
    }
    for filename, model in event_models.items():
        schema = model.model_json_schema(by_alias=True)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://ynaito.dev/schemas/ops-evidence/events/v1/{filename}"
        contracts[ROOT / "contracts/events/v1" / filename] = schema
    return contracts


def write_contracts() -> None:
    for path, contract in build_contracts().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_contracts()
