from typing import List
from fastapi import APIRouter, status

from app.modules.tables import apis
from app.modules.tables.schemas import (
    StandeeResponse,
    TableResponse,
    TableTransferResponse,
    ValidateQRResponse,
)

router = APIRouter(prefix="/tables", tags=["Tables"])

router.get("", response_model=List[TableResponse])(apis.get_tables)
router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)(apis.create_table)
router.post("/validate-qr", response_model=ValidateQRResponse)(apis.validate_table_qr)
router.get("/{table_id}", response_model=TableResponse)(apis.get_table)
router.patch("/{table_id}/status", response_model=TableResponse)(apis.update_table_status)
router.get("/{table_id}/qr")(apis.generate_table_qr_code)
router.get("/{table_id}/standee", response_model=StandeeResponse)(apis.get_table_standee_data)
router.get("/{table_id}/scan")(apis.scan_table_redirect)
router.delete("/{table_id}")(apis.delete_table)

router.add_api_route(
    "/swipe",
    apis.swipe_table_endpoint,
    methods=["POST"],
    response_model=TableTransferResponse,
    summary="Swipe / Transfer Table Session",
)

router.add_api_route(
    "/transfer",
    apis.swipe_table_endpoint,
    methods=["POST"],
    response_model=TableTransferResponse,
    summary="Transfer Table Session (Alias)",
)
