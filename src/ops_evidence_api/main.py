import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ops_evidence_api import __version__
from ops_evidence_api.api.errors import register_exception_handlers
from ops_evidence_api.api.middleware import request_id_middleware
from ops_evidence_api.api.routes import health_router, router
from ops_evidence_api.application.service import IncidentService
from ops_evidence_api.config import Settings, get_settings
from ops_evidence_api.infrastructure.database import Database
from ops_evidence_api.infrastructure.fake_runner import FakeOutboxRelay, FixtureAnalysisRunner
from ops_evidence_api.infrastructure.store import PostgresEvidenceStore


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    logging.basicConfig(level=runtime_settings.log_level)

    database = Database(runtime_settings.database_url)
    store = PostgresEvidenceStore(database.session_factory)
    service = IncidentService(store)
    relay = FakeOutboxRelay(
        store,
        FixtureAnalysisRunner(runtime_settings.fixture_root),
        poll_interval_seconds=runtime_settings.fake_runner_poll_interval_seconds,
        analysis_delay_seconds=runtime_settings.fake_runner_delay_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runtime_settings.fake_runner_enabled:
            relay.start()
        try:
            yield
        finally:
            if runtime_settings.fake_runner_enabled:
                await relay.close()
            await database.close()

    application = FastAPI(
        title="OpsEvidence API",
        summary="Evidence-grounded incident analysis with reliable asynchronous boundaries.",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.state.database = database
    application.state.incident_service = service
    application.middleware("http")(request_id_middleware)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(router)
    return application


app = create_app()
