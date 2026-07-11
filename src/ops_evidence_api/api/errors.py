import logging
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ops_evidence_api.application.errors import (
    AnalysisNotFoundError,
    IdempotencyConflictError,
    IncidentNotFoundError,
)
from ops_evidence_api.contracts.api import InvalidParameter, ProblemDetails

logger = logging.getLogger(__name__)
Handler = Callable[[Request, Exception], Awaitable[JSONResponse]]


def _problem(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    errors: list[InvalidParameter] | None = None,
) -> JSONResponse:
    problem = ProblemDetails(
        type=(f"https://ynaito.dev/problems/ops-evidence/{code.lower().replace('_', '-')}"),
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        code=code,
        errors=errors or [],
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(mode="json", by_alias=True),
        media_type="application/problem+json",
    )


async def _incident_not_found(request: Request, exc: Exception) -> JSONResponse:
    error = cast(IncidentNotFoundError, exc)
    return _problem(
        request,
        status=404,
        code="INCIDENT_NOT_FOUND",
        title="Incident not found",
        detail=str(error),
    )


async def _analysis_not_found(request: Request, exc: Exception) -> JSONResponse:
    error = cast(AnalysisNotFoundError, exc)
    return _problem(
        request,
        status=404,
        code="ANALYSIS_NOT_FOUND",
        title="Analysis not found",
        detail=str(error),
    )


async def _idempotency_conflict(request: Request, exc: Exception) -> JSONResponse:
    error = cast(IdempotencyConflictError, exc)
    return _problem(
        request,
        status=409,
        code="IDEMPOTENCY_KEY_REUSED",
        title="Idempotency key conflict",
        detail=str(error),
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    validation_error = cast(RequestValidationError, exc)
    invalid_parameters = [
        InvalidParameter(
            name=".".join(str(part) for part in item["loc"] if part not in {"body", "header"}),
            reason=str(item["msg"]),
        )
        for item in validation_error.errors()
    ]
    return _problem(
        request,
        status=422,
        code="VALIDATION_FAILED",
        title="Request validation failed",
        detail="One or more request fields are invalid.",
        errors=invalid_parameters,
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    detail = (
        error.detail if isinstance(error.detail, str) else "The request could not be completed."
    )
    return _problem(
        request,
        status=error.status_code,
        code="HTTP_ERROR",
        title="HTTP request failed",
        detail=detail,
    )


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled API error",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return _problem(
        request,
        status=500,
        code="INTERNAL_ERROR",
        title="Internal server error",
        detail="The server could not complete the request.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    handlers: dict[type[Exception], Handler] = {
        IncidentNotFoundError: _incident_not_found,
        AnalysisNotFoundError: _analysis_not_found,
        IdempotencyConflictError: _idempotency_conflict,
        RequestValidationError: _validation_error,
        StarletteHTTPException: _http_error,
        Exception: _unexpected_error,
    }
    for exception_type, handler in handlers.items():
        app.add_exception_handler(exception_type, handler)


def service_unavailable_problem(request: Request) -> JSONResponse:
    return _problem(
        request,
        status=503,
        code="DATABASE_UNAVAILABLE",
        title="Service unavailable",
        detail="The database readiness check failed.",
    )
