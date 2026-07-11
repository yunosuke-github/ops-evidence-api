import asyncio
import os
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers import load_fixture_payload

pytestmark = pytest.mark.integration


async def create_incident(client: AsyncClient, *, title: str | None = None) -> dict[str, object]:
    payload = load_fixture_payload()
    if title is not None:
        payload["title"] = title
    response = await client.post("/v1/incidents", json=payload)
    assert response.status_code == 201, response.text
    assert response.headers["location"].endswith(response.json()["id"])
    return response.json()


async def test_incident_and_analysis_creation_are_idempotent(client: AsyncClient) -> None:
    incident = await create_incident(client)
    path = f"/v1/incidents/{incident['id']}/analyses"

    first, replay = await asyncio.gather(
        client.post(path, headers={"Idempotency-Key": "concurrent-key-001"}),
        client.post(path, headers={"Idempotency-Key": "concurrent-key-001"}),
    )

    assert first.status_code == 202, first.text
    assert replay.status_code == 202, replay.text
    assert first.json()["id"] == replay.json()["id"]
    assert {first.headers["idempotency-replayed"], replay.headers["idempotency-replayed"]} == {
        "false",
        "true",
    }


async def test_idempotency_key_reuse_for_another_incident_returns_conflict(
    client: AsyncClient,
) -> None:
    first_incident = await create_incident(client, title="First")
    second_incident = await create_incident(client, title="Second")
    headers = {"Idempotency-Key": "cross-incident-key"}
    first = await client.post(
        f"/v1/incidents/{first_incident['id']}/analyses",
        headers=headers,
    )
    conflict = await client.post(
        f"/v1/incidents/{second_incident['id']}/analyses",
        headers=headers,
    )

    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.headers["content-type"].startswith("application/problem+json")
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_fake_runner_completes_the_bundled_scenario(fake_client: AsyncClient) -> None:
    incident = await create_incident(fake_client)
    started = await fake_client.post(
        f"/v1/incidents/{incident['id']}/analyses",
        headers={"Idempotency-Key": "fake-runner-key"},
    )
    assert started.status_code == 202
    analysis = started.json()

    for _ in range(100):
        current = await fake_client.get(f"/v1/analyses/{analysis['id']}")
        assert current.status_code == 200
        analysis = current.json()
        if analysis["status"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.02)

    assert analysis["status"] == "completed"
    assert analysis["result"]["hypotheses"][0]["evidenceScore"] == 88


async def test_unknown_resource_and_validation_errors_use_problem_details(
    client: AsyncClient,
) -> None:
    missing = await client.get(f"/v1/analyses/{uuid4()}")
    missing_incident = await client.get(f"/v1/incidents/{uuid4()}")
    missing_route = await client.get("/not-a-route")
    invalid = await client.post("/v1/incidents", json={"title": ""})

    assert missing.status_code == 404
    assert missing.json()["code"] == "ANALYSIS_NOT_FOUND"
    assert missing_incident.status_code == 404
    assert missing_incident.json()["code"] == "INCIDENT_NOT_FOUND"
    assert missing_route.status_code == 404
    assert missing_route.json()["code"] == "HTTP_ERROR"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_FAILED"
    assert invalid.json()["errors"]


async def test_get_incident_returns_created_metadata(client: AsyncClient) -> None:
    incident = await create_incident(client)

    response = await client.get(f"/v1/incidents/{incident['id']}")

    assert response.status_code == 200
    assert response.json() == incident


async def test_unknown_fake_scenario_reaches_a_safe_failed_state(
    fake_client: AsyncClient,
) -> None:
    payload = load_fixture_payload()
    payload["scenarioId"] = "unknown-scenario"
    created = await fake_client.post("/v1/incidents", json=payload)
    started = await fake_client.post(
        f"/v1/incidents/{created.json()['id']}/analyses",
        headers={"Idempotency-Key": "unknown-scenario-key"},
    )
    analysis = started.json()

    for _ in range(100):
        current = await fake_client.get(f"/v1/analyses/{analysis['id']}")
        analysis = current.json()
        if analysis["status"] == "failed":
            break
        await asyncio.sleep(0.02)

    assert analysis["status"] == "failed"
    assert analysis["failure"] == {
        "code": "UNSUPPORTED_SCENARIO",
        "detail": "No bundled result exists for scenario 'unknown-scenario'.",
        "retryable": False,
    }


async def test_health_endpoints_include_request_ids(client: AsyncClient) -> None:
    live = await client.get("/health/live", headers={"X-Request-ID": "test-request-001"})
    ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.headers["x-request-id"] == "test-request-001"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok"}


async def test_analysis_and_outbox_are_created_together(
    client: AsyncClient,
) -> None:
    incident = await create_incident(client)
    response = await client.post(
        f"/v1/incidents/{incident['id']}/analyses",
        headers={"Idempotency-Key": "atomic-outbox-key"},
    )
    assert response.status_code == 202

    database_url = os.environ["OPS_TEST_DATABASE_URL"]
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT a.status, o.event_type, o.published_at "
                    "FROM analyses a JOIN outbox_events o ON o.analysis_id = a.id "
                    "WHERE a.id = :analysis_id"
                ),
                {"analysis_id": response.json()["id"]},
            )
        ).one()
    await engine.dispose()

    assert row.status == "queued"
    assert row.event_type == "analysis.requested"
    assert row.published_at is None
