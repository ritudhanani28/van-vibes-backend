from collections.abc import Mapping
import re
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
    field_errors: dict[str, str] | None = None,
) -> JSONResponse:
    content = {
        "success": False,
        "statusCode": status_code,
        "message": message,
        "errors": errors or [],
        "data": {},
    }
    if field_errors is not None:
        content["fieldErrors"] = field_errors
    return JSONResponse(
        status_code=status_code,
        headers=dict(headers) if headers else None,
        content=content,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues: list[dict[str, str]] = []
        field_errors: dict[str, str] = {}

        for e in exc.errors():
            loc = e.get("loc", ())
            field = str(loc[-1]) if loc else ""
            raw_msg = str(e.get("msg", ""))

            # Clean up Pydantic error prefixes and regex pattern errors
            if raw_msg.startswith("Value error, "):
                clean_msg = raw_msg[len("Value error, "):].strip()
            elif any(k in field.lower() for k in ("mobile", "contact", "phone")) and any(
                p in raw_msg for p in ("String should match pattern", "at least", "at most", "string_too_short", "string_too_long")
            ):
                clean_msg = "Phone number must contain exactly 10 digits"
            elif "Field required" in raw_msg:
                field_human = field.replace("_", " ").strip()
                clean_msg = f"{field_human.capitalize()} is required" if field_human else "This field is required"
            else:
                clean_msg = raw_msg

            issues.append({"field": field, "message": clean_msg})
            if field and field not in field_errors:
                field_errors[field] = clean_msg

        general_msg = "Validation failed"
        if len(issues) == 1 and issues[0]["message"]:
            general_msg = issues[0]["message"]

        api_logger.warning("Request validation failed (422): %s", issues)
        return _error_response(422, general_msg, errors=issues, field_errors=field_errors)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            detail_dict = exc.detail
            msg = str(detail_dict.get("message", "Request failed"))
            api_logger.warning("HTTPException [%d]: %s", exc.status_code, msg)
            content = {
                "success": False,
                "statusCode": exc.status_code,
                "message": msg,
                "errors": detail_dict.get("errors", []),
                "data": detail_dict,
                **detail_dict,
            }
            return JSONResponse(
                status_code=exc.status_code,
                headers=dict(exc.headers) if exc.headers else None,
                content=content,
            )
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        if exc.status_code >= 500:
            api_logger.error("HTTPException [%d]: %s", exc.status_code, detail)
        else:
            api_logger.warning("HTTPException [%d]: %s", exc.status_code, detail)
        return _error_response(exc.status_code, detail, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        api_logger.exception("Unhandled server exception at %s %s: %s", request.method, request.url.path, exc)
        return _error_response(
            500,
            "An unexpected error occurred. Please try again later.",
        )
