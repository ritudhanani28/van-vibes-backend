from fastapi import APIRouter
from app.modules.settings.apis import get_cafe_settings_endpoint, update_cafe_settings_endpoint
from app.modules.settings.schemas import CafeSettingsResponse

router = APIRouter(prefix="/settings", tags=["Cafe Settings"])

router.add_api_route(
    "",
    get_cafe_settings_endpoint,
    methods=["GET"],
    response_model=CafeSettingsResponse,
    summary="Get Cafe Settings",
)

router.add_api_route(
    "",
    update_cafe_settings_endpoint,
    methods=["PUT"],
    response_model=CafeSettingsResponse,
    summary="Update Cafe Settings",
)
