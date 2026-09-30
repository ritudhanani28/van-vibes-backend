from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.websocket.manager import ws_manager


class OrderService:
    """Centralized service responsible for validating and executing order status transitions."""

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
        order = db.query(Order).filter(Order.id == order_id).first()
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

        order.status = target_status
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)

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
        """Chef marks incoming order as Done: transitions ACCEPTED -> IN_KITCHEN (Accepted / In Kitchen)."""
        return await cls.transition_order(db, order_id, OrderStatus.IN_KITCHEN.value)

    @classmethod
    async def serve_order(cls, db: Session, order_id: str) -> Order:
        """Serve an order: ACCEPTED -> SERVED"""
        return await cls.transition_order(db, order_id, OrderStatus.SERVED.value)

    @classmethod
    async def complete_order(cls, db: Session, order_id: str) -> Order:
        """Complete an order: ACCEPTED -> COMPLETED"""
        return await cls.transition_order(db, order_id, OrderStatus.COMPLETED.value)
