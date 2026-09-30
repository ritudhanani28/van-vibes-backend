import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class StandardResponseMiddleware(BaseHTTPMiddleware):
    """Standardizes all HTTP JSON responses into a consistent API format.

    - Wraps successful and error JSON responses as:
    {
        "success": bool,
        "statusCode": int,
        "message": str,
        "errors": [],
        "data": ...
    }
    - Skips OpenAPI, Swagger, ReDoc, and Admin endpoints to avoid breaking
    documentation or admin responses.
    - Leaves non-JSON responses (e.g., HTML, files, streaming) unchanged.
    - Preserves important response headers (authentication, rate limits, etc.)
    while rebuilding the JSON response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            "openapi.json" in request.url.path
            or "/docs" in request.url.path
            or "/redoc" in request.url.path
            or "/admin" in request.url.path
        ):
            return await call_next(request)

        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response

        body = b""
        body_iterator = getattr(response, "body_iterator", None)
        if body_iterator is not None:
            async for chunk in body_iterator:
                body += chunk
        elif hasattr(response, "body"):
            body = getattr(response, "body", b"")

        payload: Any
        try:
            payload = json.loads(body.decode()) if body else None
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict) and {
            "success",
            "statusCode",
            "message",
            "errors",
            "data",
        }.issubset(payload.keys()):
            wrapped = payload
        else:
            message = ""
            data = payload
            if isinstance(payload, dict):
                explicit_message = payload.pop("message", "")
                detail = payload.get("detail")

                if isinstance(detail, dict):
                    message = str(explicit_message or detail.get("error", ""))
                    data = detail
                else:
                    message = str(explicit_message) or str(detail or "")
                    if "data" in payload and len(payload) == 1:
                        data = payload["data"]
                    else:
                        data = payload

                if (
                    "data" in payload
                    and len(payload) == 1
                    and not isinstance(detail, dict)
                ):
                    data = payload["data"]

            wrapped = {
                "success": 200 <= response.status_code < 400,
                "statusCode": response.status_code,
                "message": message,
                "errors": [],
                "data": (
                    data
                    if data is not None
                    and (
                        200 <= response.status_code < 400
                        or (
                            isinstance(data, dict)
                            and isinstance(payload, dict)
                            and isinstance(payload.get("detail"), dict)
                        )
                    )
                    else {}
                ),
            }

        preserved = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }
        return JSONResponse(
            content=wrapped, status_code=response.status_code, headers=preserved
        )
