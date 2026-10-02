from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.middleware.request_context import RequestContextMiddleware


def setup_middleware(app: FastAPI) -> None:
    """Configure CORS, Host, and Request Context middleware."""
    # Trusted Host Middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts_list,
    )

    # CORS Middleware
    allow_origin_regex = r"^https?://.*$"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )

    # Request Context Middleware (X-Request-ID, duration, request logging)
    app.add_middleware(RequestContextMiddleware)
