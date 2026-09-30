from collections.abc import Mapping

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from logger_manager import LoggerManager

api_logger = LoggerManager(folder_name="api")


def _error_response(
    status_code: int,
    message: str,
    errors: list[dict[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=dict(headers) if headers else None,
        content={
            "success": False,
            "statusCode": status_code,
            "message": message,
            "errors": errors or [],
            "data": {},
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues = [
            {
                "field": str(e.get("loc", ())[-1]) if e.get("loc") else "",
                "message": str(e.get("msg")),
            }
            for e in exc.errors()
        ]
        api_logger.warning("Request validation failed (422): %s", issues)
        return _error_response(422, "Validation failed", issues)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        if exc.status_code >= 500:
            api_logger.error("HTTPException [%d]: %s", exc.status_code, detail)
        else:
            api_logger.warning("HTTPException [%d]: %s", exc.status_code, detail)
        return _error_response(exc.status_code, detail, headers=exc.headers)
