from fastapi import APIRouter
from app.modules.health.apis import health_check

router = APIRouter()
router.add_api_route("/health", health_check, methods=["GET"], tags=["health"])
