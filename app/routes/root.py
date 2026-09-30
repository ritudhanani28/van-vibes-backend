from fastapi import APIRouter

from app.api.v1.endpoints.health import health_check
from app.core.config import settings

router = APIRouter(tags=["root"])


@router.get("/", tags=["root"])
def root():
    """Root service information."""
    return {
        "service": settings.PROJECT_NAME,
        "status": "running",
        "docs": "/docs",
    }


# Also expose /health at root level for orchestrator/docker health probes
router.add_api_route("/health", health_check, methods=["GET"], tags=["health"])
