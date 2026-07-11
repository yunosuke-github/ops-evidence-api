import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATUSES = {"completed", "failed"}


class DemoRequestError(Exception):
    pass


def load_payload(scenario: str) -> dict[str, Any]:
    fixture_dir = ROOT / "fixtures" / scenario
    raw_metadata = json.loads((fixture_dir / "incident.json").read_text(encoding="utf-8"))
    if not isinstance(raw_metadata, dict):
        raise ValueError("The incident fixture must contain a JSON object.")
    metadata = cast(dict[str, Any], raw_metadata)
    metadata["logs"] = {
        "format": "jsonl",
        "content": (fixture_dir / "logs.jsonl").read_text(encoding="utf-8"),
    }
    metadata["runbook"] = {
        "id": "runbook:db-pool-saturation",
        "title": "Database connection pool saturation",
        "content": (fixture_dir / "runbook.md").read_text(encoding="utf-8"),
    }
    return metadata


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: Any,
) -> tuple[dict[str, Any], httpx.Response]:
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise DemoRequestError(f"Network request failed: {exc}") from exc

    if not response.is_success:
        try:
            problem = response.json()
        except ValueError:
            problem = {"detail": response.text[:500]}
        raise DemoRequestError(
            f"API returned HTTP {response.status_code}: {json.dumps(problem, ensure_ascii=False)}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DemoRequestError("API returned a non-JSON success response.") from exc
    if not isinstance(payload, dict):
        raise DemoRequestError("API returned an unexpected JSON response shape.")
    return payload, response


def run_demo(base_url: str, scenario: str, timeout_seconds: float) -> dict[str, Any]:
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        incident, _ = request_json(client, "POST", "/v1/incidents", json=load_payload(scenario))
        analysis, _ = request_json(
            client,
            "POST",
            f"/v1/incidents/{incident['id']}/analyses",
            headers={"Idempotency-Key": f"demo-{uuid4().hex}"},
        )

        deadline = time.monotonic() + timeout_seconds
        while analysis.get("status") not in TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                raise DemoRequestError("Timed out waiting for the analysis to complete.")
            time.sleep(0.2)
            analysis, _ = request_json(client, "GET", f"/v1/analyses/{analysis['id']}")
        return analysis


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a bundled OpsEvidence scenario.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--scenario", default="db-pool-exhaustion")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    try:
        analysis = run_demo(args.base_url, args.scenario, args.timeout_seconds)
    except (DemoRequestError, OSError, ValueError) as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    return 0 if analysis.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
