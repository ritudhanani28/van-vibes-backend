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
    allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )
