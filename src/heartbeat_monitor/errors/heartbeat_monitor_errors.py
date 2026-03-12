from typing import Any


class HeartbeatMonitorError(Exception):
    def __init__(
            self,
            code: str,
            message: str,
            details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class HeartbeatMonitorUnexpectedError(HeartbeatMonitorError):
    code = "UNEXPECTED_ERROR"
    message = "Unexpected internal error"


class HeartbeatMonitorConflictError(HeartbeatMonitorError):
    pass


class HeartbeatMonitorNotFoundError(HeartbeatMonitorError):
    pass


class HeartbeatMonitorValidationError(HeartbeatMonitorError):
    pass


class HeartbeatMonitorUnauthorizedError(HeartbeatMonitorError):
    pass


class HeartbeatMonitorForbiddenError(HeartbeatMonitorError):
    pass


class HeartbeatMonitorBusinessLogicError(HeartbeatMonitorError):
    pass


class HeartbeatMonitorExternalServiceError(HeartbeatMonitorError):
    pass
