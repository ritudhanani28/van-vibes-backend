from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing import BillingInvoice
from app.models.dining_session import DiningSession, SessionStatus
from app.models.order import Order, OrderStatus
from app.models.table import Table
from app.websocket.manager import ws_manager


def _next_session_id(db: Session) -> str:
    """Generate sequential dining session ID e.g. DS-1001 safely."""
    all_sessions = db.query(DiningSession.id).filter(DiningSession.id.like("DS-%")).all()
    max_num = 1000
    for (sid,) in all_sessions:
        try:
            num = int(sid.replace("DS-", ""))
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            continue
    return f"DS-{max_num + 1}"


def _next_invoice_number(db: Session) -> str:
    """Generate sequential invoice number e.g. INV-2026-1001 safely."""
    all_invs = db.query(BillingInvoice.invoice_number).all()
    max_num = 1000
    for (inv_no,) in all_invs:
        try:
            parts = inv_no.split("-")
            num = int(parts[-1])
            if num > max_num:
                max_num = num
        except (ValueError, TypeError, IndexError):
            continue
    return f"INV-2026-{max_num + 1}"


class SessionService:
    """Centralized domain service for Dining Session lifecycle & Table release."""

    @classmethod
    def get_active_session(cls, db: Session, table_id: str) -> Optional[DiningSession]:
        """Find currently OPEN dining session for a table, if any."""
        return (
            db.query(DiningSession)
            .filter(DiningSession.table_id == table_id, DiningSession.status == SessionStatus.OPEN.value)
            .first()
        )

    @classmethod
    async def get_or_create_active_session(
        cls, db: Session, table_id: str
    ) -> Tuple[DiningSession, bool]:
        """
        Atomically get or create an OPEN dining session.
        If a new session is created, the physical table is marked OCCUPIED
        and real-time WebSocket update is broadcast.
        """
        table = db.query(Table).filter(Table.id == table_id, Table.is_active == True).first()
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Table '{table_id}' not found or inactive",
            )

        # 1. Check if OPEN session already exists
        existing = cls.get_active_session(db, table_id)
        if existing:
            # Ensure physical table is OCCUPIED
            if table.status != "OCCUPIED":
                table.status = "OCCUPIED"
                db.commit()
                await ws_manager.notify_table_status_updated(table.id, "OCCUPIED")
            return existing, False

        # 2. Concurrency-safe creation
        now = datetime.now(timezone.utc)
        new_session = DiningSession(
            id=_next_session_id(db),
            table_id=table.id,
            table_number=table.table_number,
            status=SessionStatus.OPEN.value,
            created_at=now,
            updated_at=now,
        )

        try:
            db.add(new_session)
            table.status = "OCCUPIED"
            db.commit()
            db.refresh(new_session)

            # Broadcast table occupied
            await ws_manager.notify_table_status_updated(table.id, "OCCUPIED")
            return new_session, True
        except IntegrityError:
            # Concurrent scan created the OPEN session in another thread/process!
            db.rollback()
            existing = cls.get_active_session(db, table_id)
            if existing:
                return existing, False
            raise

    @classmethod
    async def attach_order_to_session(
        cls, db: Session, table_id: str, requested_session_id: Optional[str] = None
    ) -> DiningSession:
        """
        Determine the valid OPEN dining session for an incoming order.
        Strictly rejects orders if session is BILL_GENERATED or CLOSED.
        """
        if requested_session_id:
            sess = db.query(DiningSession).filter(DiningSession.id == requested_session_id).first()
            if sess and sess.status == SessionStatus.OPEN.value:
                return sess
            # If requested session not found or already BILL_GENERATED / CLOSED:
            # Rule: Once bill is generated, do NOT append. Create/use a NEW dining session!

        # Auto-join or auto-create OPEN session for the table
        sess, _ = await cls.get_or_create_active_session(db, table_id)
        return sess

    @classmethod
    async def generate_final_bill(
        cls, db: Session, session_id: str, discount_percentage: float = 0.0, extra_charge: float = 0.0
    ) -> Tuple[BillingInvoice, DiningSession]:
        """
        Generate final consolidated bill for the dining session.
        Aggregates all active orders in the session.
        Transitions session to BILL_GENERATED.
        IMMEDIATELY RELEASES PHYSICAL TABLE TO AVAILABLE!
        """
        sess = db.query(DiningSession).filter(DiningSession.id == session_id).first()
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dining session '{session_id}' not found",
            )

        if sess.status == SessionStatus.CLOSED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This dining session has already been settled and closed.",
            )

        if not sess.orders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot generate bill for a dining session with no orders.",
            )

        # Aggregate orders
        valid_orders = [o for o in sess.orders if o.status != OrderStatus.CANCELLED.value]
        if not valid_orders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All orders in this session have been cancelled.",
            )

        subtotal = round(sum(o.subtotal for o in valid_orders), 2)
        tax = 0.0
        cgst_amt = 0.0
        sgst_amt = 0.0

        extra_chg = max(0.0, float(extra_charge or 0.0))
        discount_pct = max(0.0, min(100.0, float(discount_percentage or 0.0)))
        discount_amt = round(subtotal * (discount_pct / 100.0), 2)
        total = round(max(0.0, subtotal - discount_amt + extra_chg), 2)

        now = datetime.now(timezone.utc)

        # Clean up any legacy order-level draft invoices for this session
        db.query(BillingInvoice).filter(
            BillingInvoice.dining_session_id == sess.id,
            BillingInvoice.bill_type == "ORDER"
        ).delete(synchronize_session=False)

        # Upsert BillingInvoice for the session
        invoice = (
            db.query(BillingInvoice)
            .filter(BillingInvoice.dining_session_id == sess.id, BillingInvoice.bill_type == "SESSION")
            .first()
        )
        if not invoice:
            invoice = BillingInvoice(
                invoice_number=_next_invoice_number(db),
                dining_session_id=sess.id,
                order_id=valid_orders[0].id if valid_orders else None,
                bill_type="SESSION",
                subtotal=subtotal,
                cgst_rate=0.0,
                cgst_amount=cgst_amt,
                sgst_rate=0.0,
                sgst_amount=sgst_amt,
                tax_amount=tax,
                discount_percentage=discount_pct,
                discount_amount=discount_amt,
                extra_charge=extra_chg,
                total=total,
                payment_method="CASH",
                payment_status="PENDING",
                created_at=now,
            )
            db.add(invoice)
        else:
            invoice.subtotal = subtotal
            invoice.cgst_amount = cgst_amt
            invoice.sgst_amount = sgst_amt
            invoice.tax_amount = tax
            invoice.discount_percentage = discount_pct
            invoice.discount_amount = discount_amt
            invoice.extra_charge = extra_chg
            invoice.total = total
            invoice.bill_type = "SESSION"

        # Update Session state to BILL_GENERATED
        sess.status = SessionStatus.BILL_GENERATED.value
        sess.updated_at = now

        # Synchronize order totals & discount metadata
        for o in valid_orders:
            o.discount_percentage = discount_pct
            o.updated_at = now

        # CRITICAL: Physical table becomes AVAILABLE immediately!
        tbl = db.query(Table).filter(Table.id == sess.table_id).first()
        if tbl:
            tbl.status = "AVAILABLE"
            tbl.updated_at = now

        db.commit()
        db.refresh(invoice)
        db.refresh(sess)

        # Real-time WebSocket table release broadcast
        if tbl:
            await ws_manager.notify_table_status_updated(tbl.id, "AVAILABLE")

        return invoice, sess

    @classmethod
    async def settle_session_bill(
        cls, db: Session, session_id: str, payment_method: str = "CASH"
    ) -> Tuple[BillingInvoice, DiningSession]:
        """
        Mark bill PAID, transition session to CLOSED.
        Guarantees that Table status is NOT forced to AVAILABLE if another
        active OPEN session is currently running on the table.
        """
        sess = db.query(DiningSession).filter(DiningSession.id == session_id).first()
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dining session '{session_id}' not found",
            )

        invoice = (
            db.query(BillingInvoice)
            .filter(BillingInvoice.dining_session_id == sess.id)
            .first()
        )
        now = datetime.now(timezone.utc)

        if not invoice:
            # Auto-generate bill if not already generated
            invoice, sess = await cls.generate_final_bill(db, session_id, 0.0)

        # Mark invoice PAID
        invoice.payment_status = "PAID"
        invoice.payment_method = payment_method
        invoice.settled_at = now

        # Mark all orders in this session PAID
        for o in sess.orders:
            o.payment_status = "PAID"
            o.updated_at = now

        # Transition session to CLOSED
        sess.status = SessionStatus.CLOSED.value
        sess.closed_at = now
        sess.updated_at = now

        # Check if table has another active OPEN session!
        active_open_session = (
            db.query(DiningSession)
            .filter(
                DiningSession.table_id == sess.table_id,
                DiningSession.status == SessionStatus.OPEN.value,
                DiningSession.id != sess.id,
            )
            .first()
        )

        tbl = db.query(Table).filter(Table.id == sess.table_id).first()
        if tbl:
            if active_open_session:
                # Table REMAINS OCCUPIED by the newer dining session!
                tbl.status = "OCCUPIED"
            else:
                # Table is AVAILABLE
                tbl.status = "AVAILABLE"
            tbl.updated_at = now

        db.commit()
        db.refresh(invoice)
        db.refresh(sess)

        # Broadcast payment settled
        await ws_manager.notify_payment_settled(
            order_id=invoice.order_id or sess.id,
            table_id=sess.table_id,
            invoice_number=invoice.invoice_number,
            payment_method=invoice.payment_method,
        )

        if tbl and not active_open_session:
            await ws_manager.notify_table_status_updated(tbl.id, "AVAILABLE")

        return invoice, sess

    @classmethod
    async def transfer_table_session(
        cls, db: Session, source_table_id: str, dest_table_id: str
    ) -> Tuple[DiningSession, Table, Table, List[str]]:
        """
        Table Swipe / Transfer domain operation:
        Atomically transfers an active unbilled dining session and all its associated
        orders from source table to destination table.
        Releases source table to AVAILABLE, marks destination table OCCUPIED.
        Broadcasts real-time events to all clients.
        """
        if source_table_id == dest_table_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination table cannot be the same.",
            )

        source_table = (
            db.query(Table)
            .filter(Table.id == source_table_id, Table.is_active == True)
            .first()
        )
        if not source_table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source table '{source_table_id}' not found or is inactive.",
            )

        dest_table = (
            db.query(Table)
            .filter(Table.id == dest_table_id, Table.is_active == True)
            .first()
        )
        if not dest_table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination table '{dest_table_id}' not found or is inactive.",
            )

        if dest_table.status != "AVAILABLE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination Table {dest_table.table_number} is currently {dest_table.status}. Only available tables can be selected as destination.",
            )

        dest_open_session = (
            db.query(DiningSession)
            .filter(
                DiningSession.table_id == dest_table.id,
                DiningSession.status == SessionStatus.OPEN.value,
            )
            .first()
        )
        if dest_open_session:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination Table {dest_table.table_number} already has an active dining session.",
            )

        active_session = (
            db.query(DiningSession)
            .filter(
                DiningSession.table_id == source_table.id,
                DiningSession.status == SessionStatus.OPEN.value,
            )
            .first()
        )
        if not active_session:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source Table {source_table.table_number} has no active unbilled dining session.",
            )

        if active_session.status != SessionStatus.OPEN.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dining session on Table {source_table.table_number} is already {active_session.status} and cannot be transferred.",
            )

        finalized_invoice = (
            db.query(BillingInvoice)
            .filter(
                BillingInvoice.dining_session_id == active_session.id,
                BillingInvoice.payment_status == "PAID",
            )
            .first()
        )
        if finalized_invoice:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dining session on Table {source_table.table_number} has already been paid and closed.",
            )

        now = datetime.now(timezone.utc)

        # 1. Re-associate session with destination table
        active_session.table_id = dest_table.id
        active_session.table_number = dest_table.table_number
        active_session.updated_at = now

        # 2. Re-associate all orders belonging to this active session
        order_ids: List[str] = []
        for order in active_session.orders:
            order.table_id = dest_table.id
            order.table_number = dest_table.table_number
            order.updated_at = now
            order_ids.append(order.id)

        # 3. Update table statuses
        source_table.status = "AVAILABLE"
        source_table.updated_at = now

        dest_table.status = "OCCUPIED"
        dest_table.updated_at = now

        db.commit()
        db.refresh(active_session)
        db.refresh(source_table)
        db.refresh(dest_table)

        # 4. Broadcast real-time notifications
        await ws_manager.notify_table_status_updated(source_table.id, "AVAILABLE")
        await ws_manager.notify_table_status_updated(dest_table.id, "OCCUPIED")

        transfer_payload = {
            "sourceTableId": source_table.id,
            "sourceTableNumber": source_table.table_number,
            "destinationTableId": dest_table.id,
            "destinationTableNumber": dest_table.table_number,
            "sessionId": active_session.id,
            "orderIds": order_ids,
        }

        await ws_manager.broadcast_event(
            event_type="TABLE_TRANSFERRED",
            admin_payload=transfer_payload,
            chef_payload=transfer_payload,
        )

        for order in active_session.orders:
            await ws_manager.notify_order_status_updated(
                order_id=order.id,
                new_status=order.status,
                table_id=dest_table.id,
                updated_at=now.isoformat(),
            )

        return active_session, source_table, dest_table, order_ids

