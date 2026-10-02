from fastapi import APIRouter

from app.core.config import settings
from app.modules.health.apis import health_check

router = APIRouter(tags=["root"])


@router.get("/", tags=["root"])
def root():
    """Root service information with standard envelope."""
    return {
        "success": True,
        "statusCode": 200,
        "message": "Service is healthy",
        "errors": [],
        "data": {
            "service": settings.PROJECT_NAME,
            "status": "running",
            "docs": "/docs",
        },
    }


# Also expose /health at root level for orchestrator/docker health probes
router.add_api_route("/health", health_check, methods=["GET"], tags=["health"])
