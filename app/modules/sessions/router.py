from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import require_admin, require_chef_or_admin
from app.modules.sessions.apis import (
    generate_bill_endpoint,
    generate_session_bill_endpoint,
    get_bill_receipt_endpoint,
    get_billing_ledger_endpoint,
    get_dining_session_detail_endpoint,
    get_pending_invoices_endpoint,
    get_session_bill_receipt_endpoint,
    list_dining_sessions_endpoint,
    settle_bill_payment_endpoint,
    settle_session_bill_endpoint,
    start_dining_session_for_table_endpoint,
)
from app.modules.sessions.schemas import (
    BillReceiptResponse,
    DiningSessionDetailResponse,
    DiningSessionResponse,
    GenerateBillRequest,
    InvoiceResponse,
    SettlePaymentRequest,
)

# Dining Sessions Router
dining_sessions_router = APIRouter(prefix="/dining-sessions", tags=["Dining Sessions"])

dining_sessions_router.add_api_route(
    "",
    list_dining_sessions_endpoint,
    methods=["GET"],
    response_model=List[DiningSessionResponse],
    summary="List Dining Sessions",
)

dining_sessions_router.add_api_route(
    "/{session_id}",
    get_dining_session_detail_endpoint,
    methods=["GET"],
    response_model=DiningSessionDetailResponse,
    summary="Get Dining Session Detail",
)

dining_sessions_router.add_api_route(
    "/table/{table_id}/start",
    start_dining_session_for_table_endpoint,
    methods=["POST"],
    response_model=DiningSessionResponse,
    summary="Start Table Dining Session",
)


# Billing & POS Router
billing_router = APIRouter(prefix="/billing", tags=["Billing & POS"])

billing_router.add_api_route(
    "/ledger",
    get_billing_ledger_endpoint,
    methods=["GET"],
    response_model=List[InvoiceResponse],
    summary="Get Billing Ledger",
)

billing_router.add_api_route(
    "/pending",
    get_pending_invoices_endpoint,
    methods=["GET"],
    response_model=List[InvoiceResponse],
    summary="Get Pending Invoices",
)

billing_router.add_api_route(
    "/sessions/{session_id}",
    get_session_bill_receipt_endpoint,
    methods=["GET"],
    response_model=BillReceiptResponse,
    summary="Get Session Bill Receipt",
)

billing_router.add_api_route(
    "/sessions/{session_id}/generate",
    generate_session_bill_endpoint,
    methods=["POST"],
    response_model=BillReceiptResponse,
    summary="Generate Session Bill",
)

billing_router.add_api_route(
    "/sessions/{session_id}/settle",
    settle_session_bill_endpoint,
    methods=["POST"],
    response_model=InvoiceResponse,
    summary="Settle Session Bill",
)

billing_router.add_api_route(
    "/{order_id}",
    get_bill_receipt_endpoint,
    methods=["GET"],
    response_model=BillReceiptResponse,
    summary="Get Order Bill Receipt",
)

billing_router.add_api_route(
    "/{order_id}/generate",
    generate_bill_endpoint,
    methods=["POST"],
    response_model=BillReceiptResponse,
    summary="Generate Order Bill",
)

billing_router.add_api_route(
    "/{order_id}/bill",
    generate_bill_endpoint,
    methods=["POST"],
    response_model=BillReceiptResponse,
    summary="Generate Order Bill (Alias)",
)

billing_router.add_api_route(
    "/{order_id}/settle",
    settle_bill_payment_endpoint,
    methods=["POST"],
    response_model=InvoiceResponse,
    summary="Settle Order Payment",
)

# Combined Router
router = APIRouter()
router.include_router(dining_sessions_router)
router.include_router(billing_router)
