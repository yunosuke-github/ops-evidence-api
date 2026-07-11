from uuid import UUID


class ApplicationError(Exception):
    """Base class for expected application failures."""


class IncidentNotFoundError(ApplicationError):
    def __init__(self, incident_id: UUID) -> None:
        super().__init__(f"Incident {incident_id} was not found.")
        self.incident_id = incident_id


class AnalysisNotFoundError(ApplicationError):
    def __init__(self, analysis_id: UUID) -> None:
        super().__init__(f"Analysis {analysis_id} was not found.")
        self.analysis_id = analysis_id


class IdempotencyConflictError(ApplicationError):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__("The idempotency key was already used for a different request.")
        self.idempotency_key = idempotency_key
