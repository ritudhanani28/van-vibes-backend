from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_optional_current_user, require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.orders.apis import (
    accept_order_endpoint,
    cancel_order_endpoint,
    complete_order_endpoint,
    create_order_bill_endpoint,
    create_order_endpoint,
    done_order_endpoint,
    get_order_endpoint,
    list_orders_endpoint,
    serve_order_endpoint,
    update_order_status_endpoint,
)
from app.modules.orders.schemas import (
    CancelOrderRequest,
    CreateOrderRequest,
    OrderResponse,
    UpdateOrderStatusRequest,
)
from app.modules.sessions.schemas import BillReceiptResponse, GenerateBillRequest

router = APIRouter(prefix="/orders", tags=["Orders"])

router.add_api_route(
    "",
    create_order_endpoint,
    methods=["POST"],
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Customer Order",
)

router.add_api_route(
    "",
    list_orders_endpoint,
    methods=["GET"],
    summary="List Orders",
)

router.add_api_route(
    "/{order_id}",
    get_order_endpoint,
    methods=["GET"],
    summary="Get Order Details",
)

router.add_api_route(
    "/{order_id}/accept",
    accept_order_endpoint,
    methods=["POST"],
    summary="Accept Order",
)

router.add_api_route(
    "/{order_id}/done",
    done_order_endpoint,
    methods=["POST"],
    summary="Kitchen Done Order",
)

router.add_api_route(
    "/{order_id}/serve",
    serve_order_endpoint,
    methods=["POST"],
    summary="Serve Order",
)

router.add_api_route(
    "/{order_id}/complete",
    complete_order_endpoint,
    methods=["POST"],
    summary="Complete Order",
)

router.add_api_route(
    "/{order_id}/status",
    update_order_status_endpoint,
    methods=["PATCH"],
    summary="Update Order Status",
)

router.add_api_route(
    "/{order_id}/cancel",
    cancel_order_endpoint,
    methods=["POST"],
    summary="Cancel Order",
)

router.add_api_route(
    "/{order_id}/bill",
    create_order_bill_endpoint,
    methods=["POST"],
    response_model=BillReceiptResponse,
    summary="Generate Order Bill",
)
