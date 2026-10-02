from typing import List, Optional, Union
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_optional_current_user, require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.orders.crud import OrderCRUD
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.schemas import (
    CancelOrderRequest,
    ChefOrderResponse,
    CreateOrderRequest,
    OrderResponse,
    UpdateOrderStatusRequest,
)
from app.modules.orders.service import OrderService
from app.modules.sessions.schemas import BillReceiptResponse, GenerateBillRequest


def _format_order(order: Order, role: Optional[str] = None) -> Union[OrderResponse, ChefOrderResponse]:
    """Format order; strip prices if role is CHEF."""
    if role == "CHEF":
        return ChefOrderResponse.model_validate(order)
    return OrderResponse.model_validate(order)


async def create_order_endpoint(payload: CreateOrderRequest, db: Session = Depends(get_db)):
    """Public customer order placement."""
    new_order = await OrderService.create_order(db, payload)
    return OrderResponse.model_validate(new_order)


def list_orders_endpoint(
    status: Optional[str] = Query(None, description="Filter by order status"),
    table_id: Optional[str] = Query(None, description="Filter by table ID"),
    dining_session_id: Optional[str] = Query(None, description="Filter by dining session ID"),
    session_token: Optional[str] = Query(None, description="Filter by guest session token"),
    range: Optional[str] = Query(None, description="Filter by date range: today, yesterday, 30_days, month, year"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """List orders with role-based field filtering and optional date range."""
    from app.modules.dashboard.service import parse_date_range

    start_dt, end_dt = parse_date_range(range) if range else (None, None)
    orders = OrderCRUD.get_multi(
        db=db,
        status=status,
        table_id=table_id,
        dining_session_id=dining_session_id,
        session_token=session_token,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    user_role = current_user.role if current_user else None
    return [_format_order(o, role=user_role) for o in orders]


def get_order_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Retrieve single order details with role-based data projection."""
    order = OrderCRUD.get_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )
    user_role = current_user.role if current_user else None
    return _format_order(order, role=user_role)


async def accept_order_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Accept order: transitions PLACED -> ACCEPTED."""
    order = await OrderService.accept_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


async def done_order_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """Chef marks incoming order as Done: transitions ACCEPTED -> IN_KITCHEN."""
    order = await OrderService.done_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


async def serve_order_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """Serve order: transitions ACCEPTED -> SERVED."""
    order = await OrderService.serve_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


async def complete_order_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """Complete order: transitions SERVED -> COMPLETED."""
    order = await OrderService.complete_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


async def update_order_status_endpoint(
    order_id: str,
    payload: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """Transition order status via centralized OrderService."""
    order = await OrderService.transition_order(
        db=db,
        order_id=order_id,
        target_status=payload.status.upper(),
    )
    return _format_order(order, role=current_user.role)


async def cancel_order_endpoint(
    order_id: str,
    payload: Optional[CancelOrderRequest] = None,
    db: Session = Depends(get_db),
):
    """Cancel order (only permitted in PLACED stage)."""
    reason = payload.reason if payload else None
    order = await OrderService.cancel_order(db=db, order_id=order_id, reason=reason)
    return {"message": f"Order {order_id} has been cancelled", "order": OrderResponse.model_validate(order)}


async def create_order_bill_endpoint(
    order_id: str,
    payload: Optional[GenerateBillRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_chef_or_admin),
):
    """Generate or update bill for order with optional bill-level discount."""
    from app.modules.sessions.service import BillingService

    if admin.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin is authorized to generate bills and apply discounts.",
        )
    return await BillingService.generate_order_bill(db=db, order_id=order_id, payload=payload)
