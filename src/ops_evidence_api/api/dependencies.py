from typing import Annotated, cast

from fastapi import Depends, Request

from ops_evidence_api.application.service import IncidentService
from ops_evidence_api.infrastructure.database import Database


def get_incident_service(request: Request) -> IncidentService:
    return cast(IncidentService, request.app.state.incident_service)


def get_database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


IncidentServiceDependency = Annotated[IncidentService, Depends(get_incident_service)]
DatabaseDependency = Annotated[Database, Depends(get_database)]
