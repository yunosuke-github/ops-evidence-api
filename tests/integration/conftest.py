import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ops_evidence_api.config import Settings
from ops_evidence_api.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def _test_database_url() -> str:
    url = os.environ.get("OPS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("OPS_TEST_DATABASE_URL is required for PostgreSQL integration tests.")
    return url


@pytest.fixture(autouse=True)
async def reset_database() -> AsyncIterator[None]:
    engine = create_async_engine(_test_database_url())
    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE TABLE outbox_events, analyses, incidents RESTART IDENTITY CASCADE")
        )
    yield
    await engine.dispose()


async def _client(*, fake_runner_enabled: bool) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        environment="test",
        database_url=_test_database_url(),
        fake_runner_enabled=fake_runner_enabled,
        fake_runner_poll_interval_seconds=0.01,
        fake_runner_delay_seconds=0.01,
        fixture_root=ROOT / "fixtures",
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async for value in _client(fake_runner_enabled=False):
        yield value


@pytest.fixture
async def fake_client() -> AsyncIterator[AsyncClient]:
    async for value in _client(fake_runner_enabled=True):
        yield value
