from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import JSONResponse

from ops_evidence_api.api.dependencies import DatabaseDependency, IncidentServiceDependency
from ops_evidence_api.api.errors import service_unavailable_problem
from ops_evidence_api.application.models import Analysis, CreateIncidentCommand, Incident
from ops_evidence_api.contracts.api import (
    AnalysisFailure,
    AnalysisResponse,
    AnalysisResult,
    HealthResponse,
    IncidentCreate,
    IncidentResponse,
    ProblemDetails,
)

router = APIRouter(prefix="/v1")
health_router = APIRouter(prefix="/health", tags=["health"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]
Traceparent = Annotated[
    str | None,
    Header(
        alias="traceparent",
        max_length=255,
        pattern=r"^[\da-f]{2}-[\da-f]{32}-[\da-f]{16}-[\da-f]{2}$",
    ),
]


def _incident_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=incident.id,
        title=incident.title,
        scenario_id=incident.scenario_id,
        created_at=incident.created_at,
    )


def _analysis_response(analysis: Analysis) -> AnalysisResponse:
    return AnalysisResponse(
        id=analysis.id,
        incident_id=analysis.incident_id,
        status=analysis.status,
        result=AnalysisResult.model_validate(analysis.result) if analysis.result else None,
        failure=AnalysisFailure.model_validate(analysis.failure) if analysis.failure else None,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


@router.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["incidents"],
)
async def create_incident(
    payload: IncidentCreate,
    response: Response,
    service: IncidentServiceDependency,
) -> IncidentResponse:
    incident = await service.create_incident(
        CreateIncidentCommand(
            title=payload.title,
            scenario_id=payload.scenario_id,
            alert=payload.alert.model_dump(mode="json", by_alias=True),
            logs=payload.logs.model_dump(mode="json", by_alias=True),
            runbook=payload.runbook.model_dump(mode="json", by_alias=True),
        )
    )
    response.headers["Location"] = f"/v1/incidents/{incident.id}"
    return _incident_response(incident)


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    responses={404: {"model": ProblemDetails}},
    tags=["incidents"],
)
async def get_incident(
    incident_id: UUID,
    service: IncidentServiceDependency,
) -> IncidentResponse:
    return _incident_response(await service.get_incident(incident_id))


@router.post(
    "/incidents/{incident_id}/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ProblemDetails}, 409: {"model": ProblemDetails}},
    tags=["analyses"],
)
async def start_analysis(
    incident_id: UUID,
    response: Response,
    service: IncidentServiceDependency,
    idempotency_key: IdempotencyKey,
    traceparent: Traceparent = None,
) -> AnalysisResponse:
    result = await service.start_analysis(
        incident_id,
        idempotency_key=idempotency_key,
        traceparent=traceparent,
    )
    response.headers["Location"] = f"/v1/analyses/{result.analysis.id}"
    response.headers["Idempotency-Replayed"] = str(result.replayed).lower()
    return _analysis_response(result.analysis)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisResponse,
    responses={404: {"model": ProblemDetails}},
    tags=["analyses"],
)
async def get_analysis(
    analysis_id: UUID,
    service: IncidentServiceDependency,
) -> AnalysisResponse:
    return _analysis_response(await service.get_analysis(analysis_id))


@health_router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse()


@health_router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": ProblemDetails}},
)
async def readiness(
    request: Request,
    database: DatabaseDependency,
) -> HealthResponse | JSONResponse:
    if not await database.is_ready():
        return service_unavailable_problem(request)
    return HealthResponse()
