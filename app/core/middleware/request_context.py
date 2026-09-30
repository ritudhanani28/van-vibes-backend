import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core import messages
from app.core.logging_config import request_id_var, user_id_var
from app.core.security import SecurityService
from logger_manager import LoggerManager

api_logger = LoggerManager(folder_name="api")

_QUIET_PREFIXES = ("/static", "/favicon")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlates and logs every HTTP request.

    - Assigns a request id (or adopts an incoming X-Request-ID) and the
      authenticated user id (from the JWT, no DB hit) into contextvars, so
      EVERY log line emitted while handling the request carries req=/user=.
    - Logs method, path, status and duration to api.log.
    - Captures unhandled exceptions with the full stack trace (and returns a
      clean 500) — bodies and headers are never logged, so credentials can't
      leak into log files.

    Registered last in setup_middleware => outermost: it wraps CORS/session/
    response middleware too. WebSocket connections don't pass through here
    (BaseHTTPMiddleware is HTTP-only).
    """

    @staticmethod
    def _user_id_from_auth(request: Request) -> str:
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return "-"
        try:
            token = auth.split(" ", 1)[1].strip()
            payload = SecurityService.decode_token(token)
            return str(payload.get("sub") or "-")
        except Exception:  # noqa: BLE001
            return "-"  # invalid/expired token — auth layer handles rejection

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex[:12])[:64]
        req_token = request_id_var.set(request_id)
        user_token = user_id_var.set(self._user_id_from_auth(request))
        quiet = request.url.path.startswith(_QUIET_PREFIXES)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            if not quiet:
                duration_ms = (time.perf_counter() - started) * 1000
                level = (
                    api_logger.warning
                    if response.status_code >= 400
                    else api_logger.info
                )
                level(
                    messages.LOG_REQUEST_LINE,
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    request.client.host if request.client else "-",
                )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            api_logger.exception(
                messages.LOG_REQUEST_EXCEPTION_LINE,
                request.method,
                request.url.path,
                duration_ms,
                request.client.host if request.client else "-",
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "statusCode": 500,
                    "message": messages.INTERNAL_SERVER_ERROR,
                    "errors": [],
                    "data": {},
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(req_token)
            user_id_var.reset(user_token)
