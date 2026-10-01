from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings


def setup_middleware(app: FastAPI) -> None:
    """Configure CORS and Host middleware for the FastAPI application."""
    # Trusted Host Middleware - Protects against Host Header attacks
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts_list,
    )

    # CORS Middleware - Handles Cross-Origin Resource Sharing
    # Allow localhost, 127.0.0.1, LAN IPs (192.168.x.x, 10.x.x.x, 172.x.x.x), and any configured origins
    # Allow any HTTP/HTTPS origin (localhost, LAN, public IPs such as 84.247.143.242, and domains)
    allow_origin_regex = r"^https?://.*$"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )
