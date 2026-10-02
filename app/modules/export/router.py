from fastapi import APIRouter
from app.modules.export import apis

router = APIRouter(prefix="/export", tags=["Data Export"])

router.add_api_route(
    "/preview",
    apis.export_preview_endpoint,
    methods=["POST"],
    summary="Preview Export Record Counts",
)

router.add_api_route(
    "/download",
    apis.export_download_endpoint,
    methods=["POST"],
    summary="Download Exported CSV/ZIP",
)
