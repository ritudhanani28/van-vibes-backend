"""Versioned JSON API (v1).

Exposes the aggregated api_router mounted under settings.API_V1_STR (/api/v1).
"""

from app.api.v1.router import api_router

__all__ = ["api_router"]
