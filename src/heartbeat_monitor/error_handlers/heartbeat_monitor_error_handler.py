from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from heartbeat_monitor.errors import (
    HeartbeatMonitorBusinessLogicError,
    HeartbeatMonitorConflictError,
    HeartbeatMonitorError,
    HeartbeatMonitorExternalServiceError,
    HeartbeatMonitorForbiddenError,
    HeartbeatMonitorNotFoundError,
    HeartbeatMonitorUnauthorizedError,
    HeartbeatMonitorUnexpectedError,
    HeartbeatMonitorValidationError,
)


def register_error_handlers(app: FastAPI) -> None:
    async def handle_all_errors(request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, HeartbeatMonitorError):
            logger.bind(
                method=request.method,
                path=request.url.path,
                error_type=exc.__class__.__name__,
            ).exception(f"Unhandled Application Error: {exc}")

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "code": HeartbeatMonitorUnexpectedError.code,
                    "message": HeartbeatMonitorUnexpectedError.message,
                },
            )

        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        if isinstance(exc, HeartbeatMonitorNotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, HeartbeatMonitorUnauthorizedError):
            status_code = status.HTTP_401_UNAUTHORIZED
        elif isinstance(exc, HeartbeatMonitorForbiddenError):
            status_code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, HeartbeatMonitorConflictError):
            status_code = status.HTTP_409_CONFLICT
        elif isinstance(exc, (HeartbeatMonitorValidationError, HeartbeatMonitorBusinessLogicError)):
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, HeartbeatMonitorExternalServiceError):
            status_code = status.HTTP_502_BAD_GATEWAY

        logger.bind(
            method=request.method,
            path=request.url.path,
            error_code=exc.code,
        ).info(f"Business Rule Violation [{exc.code}]: {exc.message} "
               f"| Details: {exc.details}")

        return JSONResponse(
            status_code=status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    app.add_exception_handler(Exception, handle_all_errors)
