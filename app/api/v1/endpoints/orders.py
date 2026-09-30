from app.schemas.billing import BillReceiptResponse, GenerateBillRequest
from app.api.v1.endpoints.billing import generate_bill
from datetime import datetime, timezone
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_optional_current_user, require_admin, require_chef_or_admin
from app.db.session import get_db
from app.models.billing import BillingInvoice
from app.models.customer import Customer
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, OrderStatus
from app.models.table import Table
from app.models.user import User
from app.schemas.order import (
    AdminOrderResponse,
    CancelOrderRequest,
    ChefOrderResponse,
    CreateOrderRequest,
    OrderResponse,
    UpdateOrderStatusRequest,
)
from app.services.order_service import OrderService
from app.services.session_service import SessionService
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/orders", tags=["Orders"])


def _next_order_id(db: Session) -> str:
    """Generate sequential order ID e.g. VV-1003 safely using max ID."""
    all_ids = db.query(Order.id).filter(Order.id.like("VV-%")).all()
    max_num = 1000
    for (oid,) in all_ids:
        try:
            num = int(oid.replace("VV-", ""))
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            continue
    return f"VV-{max_num + 1}"


def _format_order(order: Order, role: Optional[str] = None) -> Union[OrderResponse, ChefOrderResponse]:
    """Format order; strip prices if role is CHEF."""
    if role == "CHEF":
        return ChefOrderResponse.model_validate(order)
    return OrderResponse.model_validate(order)


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: CreateOrderRequest, db: Session = Depends(get_db)):
    """
    Public customer order placement.
    Authoritative server-side price computation and database transaction.
    Automatically assigns initial status = PLACED.
    Broadcasts real-time ORDER_PLACED event.
    """
    # 1. Validate table & token
    table = db.query(Table).filter(Table.id == payload.table_id, Table.is_active == True).first()
    if not table:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table '{payload.table_id}' not found",
        )
    if table.token != payload.token and not payload.token.startswith(f"vv_sec_{table.id.lower()}_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid table security token",
        )

    # 2. Resolve or Join Dining Session (strictly rejects if bill already generated)
    session = await SessionService.attach_order_to_session(db, table.id, payload.dining_session_id)

    # 3. Upsert customer
    customer = db.query(Customer).filter(Customer.mobile == payload.customer_mobile).first()
    if not customer:
        customer = Customer(
            name=payload.customer_name,
            mobile=payload.customer_mobile,
            last_visited_at=datetime.now(timezone.utc),
        )
        db.add(customer)
    else:
        customer.name = payload.customer_name
        customer.last_visited_at = datetime.now(timezone.utc)

    # 4. Server-side authoritative price recalculation with DB discount
    order_id = _next_order_id(db)
    now = datetime.now(timezone.utc)
    order_items_to_add: List[OrderItem] = []
    subtotal = 0.0

    for item_input in payload.items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item_input.menu_item_id).first()
        if not menu_item:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Menu item '{item_input.menu_item_id}' not found",
            )
        if not menu_item.is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{menu_item.name}' is currently unavailable",
            )

        # Add add-on prices if applicable
        extra_charges = 0.0
        if item_input.selected_add_ons and menu_item.add_ons:
            add_ons_map = {ao["name"]: ao["price"] for ao in menu_item.add_ons if "name" in ao and "price" in ao}
            for ao_name in item_input.selected_add_ons:
                extra_charges += add_ons_map.get(ao_name, 0.0)

        effective_unit_price = round(float(menu_item.price) + extra_charges, 2)
        item_total = round(effective_unit_price * item_input.quantity, 2)
        subtotal = round(subtotal + item_total, 2)

        order_item = OrderItem(
            order_id=order_id,
            menu_item_id=menu_item.id,
            name=menu_item.name,
            category=menu_item.category_id,
            unit_price=effective_unit_price,
            quantity=item_input.quantity,
            item_total=item_total,
            selected_options=item_input.selected_options,
            selected_add_ons=item_input.selected_add_ons,
            special_instructions=item_input.special_instructions,
            created_at=now,
        )
        order_items_to_add.append(order_item)

    # Authoritative calculation without GST/taxes
    tax = 0.0
    total = subtotal

    # 5. Create Order with initial status PLACED linked to Dining Session
    new_order = Order(
        id=order_id,
        cafe_id="van-vibes",
        table_id=table.id,
        table_number=table.table_number,
        dining_session_id=session.id,
        session_token=payload.session_token,
        customer_name=payload.customer_name,
        customer_mobile=payload.customer_mobile,
        special_instructions=payload.special_instructions,
        status=OrderStatus.PLACED.value,
        payment_status="PENDING",
        subtotal=subtotal,
        tax=tax,
        discount_amount=0.0,
        total=total,
        created_at=now,
        updated_at=now,
    )
    db.add(new_order)
    db.flush()

    for oi in order_items_to_add:
        db.add(oi)

    # Create associated Billing Invoice
    all_invs = db.query(BillingInvoice.invoice_number).all()
    max_inv_num = 1000
    for (inv_no,) in all_invs:
        try:
            parts = inv_no.split("-")
            num = int(parts[-1])
            if num > max_inv_num:
                max_inv_num = num
        except (ValueError, TypeError, IndexError):
            continue
    inv_number = f"INV-2026-{max_inv_num + 1}"
    cgst_amt = 0.0
    sgst_amt = 0.0
    invoice = BillingInvoice(
        order_id=order_id,
        dining_session_id=session.id,
        bill_type="ORDER",
        invoice_number=inv_number,
        subtotal=subtotal,
        cgst_rate=0.0,
        cgst_amount=0.0,
        sgst_rate=0.0,
        sgst_amount=0.0,
        tax_amount=0.0,
        discount_amount=0.0,
        total=total,
        payment_method="CASH",
        payment_status="PENDING",
        created_at=now,
    )
    db.add(invoice)

    # Mark table as OCCUPIED
    table.status = "OCCUPIED"

    db.commit()
    db.refresh(new_order)

    # 5. Broadcast real-time ORDER_PLACED event
    admin_payload = OrderResponse.model_validate(new_order).model_dump(by_alias=True)
    admin_payload["createdAt"] = new_order.created_at.isoformat()
    admin_payload["updatedAt"] = new_order.updated_at.isoformat()

    chef_payload = ChefOrderResponse.model_validate(new_order).model_dump(by_alias=True)
    chef_payload["createdAt"] = new_order.created_at.isoformat()
    chef_payload["updatedAt"] = new_order.updated_at.isoformat()

    await ws_manager.notify_order_placed(
        admin_order=admin_payload,
        chef_order=chef_payload,
        table_id=table.id,
    )

    return OrderResponse.model_validate(new_order)


@router.get("")
def list_orders(
    status: Optional[str] = Query(None, description="Filter by order status"),
    table_id: Optional[str] = Query(None, description="Filter by table ID"),
    dining_session_id: Optional[str] = Query(None, description="Filter by dining session ID"),
    session_token: Optional[str] = Query(None, description="Filter by guest session token"),
    range: Optional[str] = Query(None, description="Filter by date range: today, yesterday, 30_days, month, year"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    List orders.
    - If accessed by Chef: prices and billing data are stripped at API response level.
    - If accessed by Admin or customer: full financial data included.
    - Supports date range filtering on backend (today, yesterday, 30_days, month, year).
    """
    from app.api.v1.endpoints.dashboard import parse_date_range

    query = db.query(Order)

    if status and status.upper() != "ALL":
        query = query.filter(Order.status == status.upper())

    if table_id:
        query = query.filter(Order.table_id == table_id)

    if dining_session_id:
        query = query.filter(Order.dining_session_id == dining_session_id)

    if session_token:
        query = query.filter(Order.session_token == session_token)

    if range:
        start_dt, end_dt = parse_date_range(range)
        if start_dt and end_dt:
            query = query.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)

    orders = query.order_by(Order.created_at.desc()).all()

    user_role = current_user.role if current_user else None
    return [_format_order(o, role=user_role) for o in orders]


@router.get("/{order_id}")
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Retrieve single order details with role-based data projection."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )
    user_role = current_user.role if current_user else None
    return _format_order(order, role=user_role)


@router.post("/{order_id}/accept")
async def accept_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Accept order: transitions PLACED -> ACCEPTED.
    Enforces role authorization, verifies current state is PLACED, broadcasts ORDER_ACCEPTED.
    """
    order = await OrderService.accept_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


@router.post("/{order_id}/done")
async def done_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """
    Chef marks incoming order as Done: transitions ACCEPTED -> IN_KITCHEN.
    Broadcasts ORDER_IN_KITCHEN and ORDER_STATUS_UPDATED.
    """
    order = await OrderService.done_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


@router.post("/{order_id}/serve")
async def serve_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """
    Serve order: transitions ACCEPTED -> SERVED.
    Enforces role authorization, verifies current state is ACCEPTED, broadcasts ORDER_SERVED.
    """
    order = await OrderService.serve_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


@router.post("/{order_id}/complete")
async def complete_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """
    Complete order: transitions SERVED -> COMPLETED.
    Enforces role authorization, verifies current state is SERVED, broadcasts ORDER_COMPLETED.
    """
    order = await OrderService.complete_order(db=db, order_id=order_id)
    return _format_order(order, role=current_user.role)


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    payload: UpdateOrderStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_chef_or_admin),
):
    """
    Transition order status via centralized OrderService.
    Rejects invalid state machine transitions.
    """
    order = await OrderService.transition_order(
        db=db,
        order_id=order_id,
        target_status=payload.status.upper(),
    )
    return _format_order(order, role=current_user.role)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    payload: Optional[CancelOrderRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Cancel order.
    Customers can only cancel when order is still in PLACED status.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    if order.status != OrderStatus.PLACED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel order in '{order.status}' stage. Order has already been accepted or progressed.",
        )

    order = await OrderService.transition_order(db=db, order_id=order_id, target_status=OrderStatus.CANCELLED.value)

    return {"message": f"Order {order_id} has been cancelled", "order": OrderResponse.model_validate(order)}

@router.post("/{order_id}/bill", response_model=BillReceiptResponse)
async def create_order_bill(
    order_id: str,
    payload: Optional[GenerateBillRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_chef_or_admin),
):
    """Generate or update bill for order with optional bill-level discount."""
    if admin.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin is authorized to generate bills and apply discounts.",
        )
    return await generate_bill(order_id=order_id, payload=payload, db=db, admin=admin)
