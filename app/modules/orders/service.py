from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.menu.models import MenuItem
from app.modules.orders.crud import CustomerCRUD, OrderCRUD
from app.modules.orders.models import Customer, Order, OrderItem, OrderStatus
from app.modules.orders.schemas import (
    ChefOrderResponse,
    CreateOrderRequest,
    OrderResponse,
)
from app.modules.tables.models import Table
from app.modules.notifications.manager import ws_manager


class OrderService:
    """Centralized service responsible for validating and executing order placement, lifecycle transitions, and events."""

    ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
        OrderStatus.PLACED.value: [OrderStatus.ACCEPTED.value, OrderStatus.CANCELLED.value],
        OrderStatus.ACCEPTED.value: [OrderStatus.IN_KITCHEN.value, OrderStatus.COMPLETED.value],
        OrderStatus.IN_KITCHEN.value: [OrderStatus.COMPLETED.value],
        OrderStatus.SERVED.value: [OrderStatus.COMPLETED.value],
        OrderStatus.COMPLETED.value: [],
        OrderStatus.CANCELLED.value: [],
    }

    @classmethod
    def validate_transition(cls, current_status: str, target_status: str) -> None:
        """
        Validate whether transitioning from current_status to target_status is permitted.
        Raises HTTP 400 Bad Request if illegal.
        """
        allowed_next = cls.ALLOWED_TRANSITIONS.get(current_status, [])
        if target_status not in allowed_next and target_status != current_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid transition from '{current_status}' to '{target_status}'. Allowed next: {allowed_next}",
            )

    @classmethod
    async def transition_order(
        cls,
        db: Session,
        order_id: str,
        target_status: str,
    ) -> Order:
        """
        Perform verified status transition with idempotency safeguards and WebSocket broadcasts.
        """
        order = OrderCRUD.get_by_id(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' not found",
            )

        current_st = order.status

        # Idempotent: If order is already in the target status, return it safely
        if current_st == target_status:
            return order

        # Enforce transition rules
        cls.validate_transition(current_st, target_status)

        order = OrderCRUD.update_status(db, order, target_status)

        # Broadcast specific domain event
        iso_updated_at = order.updated_at.isoformat()
        if target_status == OrderStatus.ACCEPTED.value:
            await ws_manager.notify_order_accepted(
                order_id=order.id,
                table_id=order.table_id,
                updated_at=iso_updated_at,
            )
        elif target_status == OrderStatus.IN_KITCHEN.value:
            payload = {
                "orderId": order.id,
                "order_id": order.id,
                "tableId": order.table_id,
                "status": "IN_KITCHEN",
                "updatedAt": iso_updated_at,
            }
            await ws_manager.broadcast_event(
                event_type="ORDER_IN_KITCHEN",
                admin_payload=payload,
                chef_payload=payload,
                table_id=order.table_id,
            )
        elif target_status == OrderStatus.SERVED.value:
            await ws_manager.notify_order_served(
                order_id=order.id,
                table_id=order.table_id,
                updated_at=iso_updated_at,
            )
        elif target_status == OrderStatus.COMPLETED.value:
            await ws_manager.notify_order_completed(
                order_id=order.id,
                table_id=order.table_id,
                updated_at=iso_updated_at,
            )

        # Broadcast general status updated event
        await ws_manager.notify_order_status_updated(
            order_id=order.id,
            new_status=order.status,
            table_id=order.table_id,
            updated_at=iso_updated_at,
        )

        return order

    @classmethod
    async def accept_order(cls, db: Session, order_id: str) -> Order:
        """Accept an order: PLACED -> ACCEPTED"""
        return await cls.transition_order(db, order_id, OrderStatus.ACCEPTED.value)

    @classmethod
    async def done_order(cls, db: Session, order_id: str) -> Order:
        """Chef marks incoming order as Done: transitions ACCEPTED -> IN_KITCHEN."""
        return await cls.transition_order(db, order_id, OrderStatus.IN_KITCHEN.value)

    @classmethod
    async def serve_order(cls, db: Session, order_id: str) -> Order:
        """Serve an order: ACCEPTED -> SERVED"""
        return await cls.transition_order(db, order_id, OrderStatus.SERVED.value)

    @classmethod
    async def complete_order(cls, db: Session, order_id: str) -> Order:
        """Complete an order: ACCEPTED -> COMPLETED"""
        return await cls.transition_order(db, order_id, OrderStatus.COMPLETED.value)

    @classmethod
    async def cancel_order(cls, db: Session, order_id: str, reason: Optional[str] = None) -> Order:
        """Cancel an order when in PLACED stage."""
        order = OrderCRUD.get_by_id(db, order_id)
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

        return await cls.transition_order(db, order_id, target_status=OrderStatus.CANCELLED.value)

    @classmethod
    async def create_order(cls, db: Session, payload: CreateOrderRequest) -> Order:
        """
        Public customer order placement.
        Authoritative server-side price computation and database transaction.
        Automatically assigns initial status = PLACED.
        Broadcasts real-time ORDER_PLACED event.
        """
        from app.modules.sessions.service import SessionService
        from app.modules.sessions.models import BillingInvoice

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

        # 2. Resolve or Join Dining Session
        session = await SessionService.attach_order_to_session(db, table.id, payload.dining_session_id)

        # 3. Upsert customer
        CustomerCRUD.upsert(db, payload.customer_name, payload.customer_mobile)

        # 4. Server-side authoritative price recalculation with DB discount
        order_id = OrderCRUD.next_order_id(db)
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

        # 6. Auto-generate draft BillingInvoice for POS ledger
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

        # 7. Broadcast real-time ORDER_PLACED event
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

        return new_order
