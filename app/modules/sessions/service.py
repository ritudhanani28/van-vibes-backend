from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.orders.models import Order, OrderStatus
from app.modules.sessions.crud import BillingCRUD, SessionCRUD
from app.modules.sessions.models import BillingInvoice, DiningSession, SessionStatus
from app.modules.sessions.schemas import (
    BillReceiptItem,
    BillReceiptResponse,
    GenerateBillRequest,
    InvoiceResponse,
    SettlePaymentRequest,
)
from app.modules.tables.models import Table
from app.modules.notifications.manager import ws_manager


class SessionService:
    """Centralized domain service for Dining Session lifecycle & Table release."""

    @classmethod
    def get_active_session(cls, db: Session, table_id: str) -> Optional[DiningSession]:
        """Find currently OPEN dining session for a table, if any."""
        return SessionCRUD.get_active_by_table(db, table_id)

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
            id=SessionCRUD.next_session_id(db),
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
            sess = SessionCRUD.get_by_id(db, requested_session_id)
            if sess and sess.status == SessionStatus.OPEN.value:
                return sess

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
        sess = SessionCRUD.get_by_id(db, session_id)
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

        invoice = BillingCRUD.get_invoice_by_session(db, sess.id, bill_type="SESSION")
        if not invoice:
            invoice = BillingInvoice(
                invoice_number=BillingCRUD.next_invoice_number(db),
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

        sess.status = SessionStatus.BILL_GENERATED.value
        sess.updated_at = now

        for o in valid_orders:
            o.discount_percentage = discount_pct
            o.updated_at = now

        tbl = db.query(Table).filter(Table.id == sess.table_id).first()
        if tbl:
            tbl.status = "AVAILABLE"
            tbl.updated_at = now

        db.commit()
        db.refresh(invoice)
        db.refresh(sess)

        if tbl:
            await ws_manager.notify_table_status_updated(tbl.id, "AVAILABLE")

        return invoice, sess

    @classmethod
    async def settle_session_bill(
        cls, db: Session, session_id: str, payment_method: str = "CASH"
    ) -> Tuple[BillingInvoice, DiningSession]:
        """Mark bill PAID, transition session to CLOSED."""
        sess = SessionCRUD.get_by_id(db, session_id)
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dining session '{session_id}' not found",
            )

        invoice = db.query(BillingInvoice).filter(BillingInvoice.dining_session_id == sess.id).first()
        now = datetime.now(timezone.utc)

        if not invoice:
            invoice, sess = await cls.generate_final_bill(db, session_id, 0.0)

        invoice.payment_status = "PAID"
        invoice.payment_method = payment_method
        invoice.settled_at = now

        for o in sess.orders:
            o.payment_status = "PAID"
            o.updated_at = now

        sess.status = SessionStatus.CLOSED.value
        sess.closed_at = now
        sess.updated_at = now

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
            tbl.status = "OCCUPIED" if active_open_session else "AVAILABLE"
            tbl.updated_at = now

        db.commit()
        db.refresh(invoice)
        db.refresh(sess)

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


class BillingService:
    """Centralized billing computation and settlement logic."""

    @classmethod
    def format_session_receipt(cls, session: DiningSession, invoice: Optional[BillingInvoice] = None) -> BillReceiptResponse:
        valid_orders = [o for o in session.orders if o.status != OrderStatus.CANCELLED.value]
        items_map = {}
        for o in valid_orders:
            for it in o.items:
                key = it.name
                if key in items_map:
                    items_map[key]["quantity"] += it.quantity
                    items_map[key]["total_price"] = round(items_map[key]["total_price"] + it.item_total, 2)
                else:
                    items_map[key] = {
                        "name": it.name,
                        "quantity": it.quantity,
                        "unit_price": it.unit_price,
                        "total_price": it.item_total,
                    }

        receipt_items = [
            BillReceiptItem(
                name=v["name"],
                quantity=v["quantity"],
                unit_price=v["unit_price"],
                total_price=v["total_price"],
            )
            for v in items_map.values()
        ]

        subtotal = round(sum(o.subtotal for o in valid_orders), 2)
        tax = round(subtotal * 0.05, 2)
        cgst = round(tax / 2, 2)
        sgst = round(tax - cgst, 2)
        session_inv = invoice if (invoice and invoice.bill_type == "SESSION") else None
        disc_pct = session_inv.discount_percentage if session_inv else 0.0
        disc_amt = session_inv.discount_amount if session_inv else round(subtotal * (disc_pct / 100.0), 2)
        extra_chg = session_inv.extra_charge if session_inv else 0.0
        total = session_inv.total if session_inv else round(max(0.0, subtotal + tax - disc_amt + extra_chg), 2)
        pay_st = session_inv.payment_status if session_inv else ("PAID" if session.status == SessionStatus.CLOSED.value else "PENDING")
        inv_num = session_inv.invoice_number if session_inv else f"BILL-{session.id}"
        created_str = (session_inv.created_at if session_inv else session.created_at).strftime("%d %b %Y, %I:%M %p")

        cust_name = valid_orders[0].customer_name if valid_orders else "Dining Guests"
        cust_mobile = valid_orders[0].customer_mobile if valid_orders else "--"

        return BillReceiptResponse(
            bill_number=inv_num,
            order_id=valid_orders[0].id if valid_orders else session.id,
            dining_session_id=session.id,
            order_ids=[o.id for o in valid_orders],
            table_number=session.table_number,
            customer_name=cust_name,
            customer_mobile=cust_mobile,
            special_instructions=None,
            items=receipt_items,
            subtotal=subtotal,
            cgst=cgst,
            sgst=sgst,
            tax_amount=tax,
            discount_percentage=disc_pct,
            discount_amount=disc_amt,
            extra_charge=extra_chg,
            total=total,
            payment_status=pay_st,
            created_at=created_str,
            session_status=session.status,
            table_status=session.table.status if session.table else None,
        )

    @classmethod
    async def generate_order_bill(
        cls,
        db: Session,
        order_id: str,
        payload: Optional[GenerateBillRequest] = None,
    ) -> BillReceiptResponse:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' not found",
            )

        subtotal = round(sum(oi.item_total for oi in order.items), 2)
        tax = 0.0
        cgst = 0.0
        sgst = 0.0

        disc_pct = 0.0
        extra_chg = 0.0
        if payload:
            if payload.discount_percentage is not None:
                disc_pct = float(payload.discount_percentage)
            elif payload.discount_amount is not None and subtotal > 0:
                disc_pct = round((float(payload.discount_amount) / subtotal) * 100.0, 2)
            if payload.extra_charge is not None:
                extra_chg = max(0.0, float(payload.extra_charge))

        if disc_pct < 0.0 or disc_pct > 100.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discount percentage must be between 0 and 100%.",
            )

        disc_amt = round(subtotal * (disc_pct / 100.0), 2)
        final_total = max(0.0, round(subtotal - disc_amt + extra_chg, 2))

        invoice = db.query(BillingInvoice).filter(BillingInvoice.order_id == order_id).first()
        if not invoice:
            invoice = BillingInvoice(
                order_id=order.id,
                invoice_number=f"INV-2026-{order.id}",
                subtotal=subtotal,
                cgst_rate=0.0,
                cgst_amount=cgst,
                sgst_rate=0.0,
                sgst_amount=sgst,
                tax_amount=tax,
                discount_percentage=disc_pct,
                discount_amount=disc_amt,
                extra_charge=extra_chg,
                total=final_total,
                payment_method="CASH",
                payment_status="PENDING",
                created_at=datetime.now(timezone.utc),
            )
            db.add(invoice)
        else:
            invoice.subtotal = subtotal
            invoice.cgst_amount = cgst
            invoice.sgst_amount = sgst
            invoice.tax_amount = tax
            invoice.discount_percentage = disc_pct
            invoice.discount_amount = disc_amt
            invoice.extra_charge = extra_chg
            invoice.total = final_total

        order.subtotal = subtotal
        order.tax = tax
        order.discount_percentage = disc_pct
        order.discount_amount = disc_amt
        order.extra_charge = extra_chg
        order.total = final_total
        order.updated_at = datetime.now(timezone.utc)

        if order.dining_session_id:
            sess = db.query(DiningSession).filter(DiningSession.id == order.dining_session_id).first()
            if sess and sess.status == SessionStatus.OPEN.value:
                sess.status = SessionStatus.BILL_GENERATED.value
                sess.updated_at = datetime.now(timezone.utc)

        tbl = db.query(Table).filter(Table.id == order.table_id).first()
        if tbl:
            tbl.status = "AVAILABLE"
            tbl.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(order)
        if invoice:
            db.refresh(invoice)

        if tbl:
            await ws_manager.notify_table_status_updated(tbl.id, "AVAILABLE")

        items = [
            BillReceiptItem(
                name=oi.name,
                quantity=oi.quantity,
                unit_price=oi.unit_price,
                total_price=oi.item_total,
                notes=oi.special_instructions,
            )
            for oi in order.items
        ]

        bill_number = invoice.invoice_number if invoice else f"BILL-{order.id}"

        return BillReceiptResponse(
            bill_number=bill_number,
            order_id=order.id,
            table_number=order.table_number or 0,
            customer_name=order.customer_name,
            customer_mobile=order.customer_mobile,
            special_instructions=order.special_instructions,
            items=items,
            subtotal=subtotal,
            cgst=cgst,
            sgst=sgst,
            tax_amount=tax,
            discount_percentage=disc_pct,
            discount_amount=disc_amt,
            extra_charge=extra_chg,
            total=final_total,
            payment_status=order.payment_status,
            created_at=order.created_at.isoformat(),
            session_status=order.dining_session.status if order.dining_session else None,
            table_status=db.query(Table.status).filter(Table.id == order.table_id).scalar(),
        )

    @classmethod
    async def settle_order_payment(
        cls,
        db: Session,
        order_id: str,
        payload: SettlePaymentRequest,
    ) -> InvoiceResponse:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' not found",
            )

        invoice = db.query(BillingInvoice).filter(BillingInvoice.order_id == order_id).first()
        if not invoice:
            tax = order.tax
            cgst_amt = round(tax / 2, 2)
            sgst_amt = round(tax - cgst_amt, 2)
            invoice = BillingInvoice(
                order_id=order.id,
                invoice_number=f"INV-2026-{order.id}",
                subtotal=order.subtotal,
                cgst_rate=0.0,
                cgst_amount=cgst_amt,
                sgst_rate=0.0,
                sgst_amount=sgst_amt,
                tax_amount=tax,
                discount_percentage=getattr(order, "discount_percentage", 0.0) or 0.0,
                discount_amount=order.discount_amount or 0.0,
                total=order.total,
                payment_method=payload.payment_method,
                payment_status="PAID",
                settled_at=datetime.now(timezone.utc),
            )
            db.add(invoice)
        else:
            invoice.payment_method = payload.payment_method
            invoice.payment_status = "PAID"
            invoice.settled_at = datetime.now(timezone.utc)

        order.payment_status = "PAID"
        order.updated_at = datetime.now(timezone.utc)

        if order.dining_session_id:
            sess = db.query(DiningSession).filter(DiningSession.id == order.dining_session_id).first()
            if sess:
                valid_orders = [o for o in sess.orders if o.status != OrderStatus.CANCELLED.value]
                all_paid = len(valid_orders) > 0 and all(
                    (o.payment_status == "PAID" or o.id == order.id) for o in valid_orders
                )
                if all_paid:
                    sess.status = SessionStatus.CLOSED.value
                    sess.closed_at = datetime.now(timezone.utc)
                    sess.updated_at = datetime.now(timezone.utc)
                    db.flush()

        if order.table_id:
            active_open_session = (
                db.query(DiningSession)
                .filter(
                    DiningSession.table_id == order.table_id,
                    DiningSession.status == SessionStatus.OPEN.value,
                )
                .first()
            )
            tbl = db.query(Table).filter(Table.id == order.table_id).first()
            if tbl:
                if not active_open_session:
                    tbl.status = "AVAILABLE"
                    await ws_manager.notify_table_status_updated(tbl.id, "AVAILABLE")
                else:
                    tbl.status = "OCCUPIED"

        db.commit()
        db.refresh(invoice)

        await ws_manager.notify_payment_settled(
            order_id=order.id,
            table_id=order.table_id,
            invoice_number=invoice.invoice_number,
            payment_method=invoice.payment_method,
        )

        return InvoiceResponse(
            id=invoice.id,
            order_id=invoice.order_id,
            invoice_number=invoice.invoice_number,
            table_number=order.table_number,
            customer_name=order.customer_name,
            subtotal=invoice.subtotal,
            cgst_rate=invoice.cgst_rate,
            cgst_amount=invoice.cgst_amount,
            sgst_rate=invoice.sgst_rate,
            sgst_amount=invoice.sgst_amount,
            tax_amount=invoice.tax_amount,
            discount_percentage=invoice.discount_percentage,
            discount_amount=invoice.discount_amount,
            total=invoice.total,
            payment_method=invoice.payment_method,
            payment_status=invoice.payment_status,
            settled_at=invoice.settled_at,
            created_at=invoice.created_at,
        )
