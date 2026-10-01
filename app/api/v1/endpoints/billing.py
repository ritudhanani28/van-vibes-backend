from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.billing import BillingInvoice
from app.models.dining_session import DiningSession, SessionStatus
from app.models.order import Order, OrderStatus
from app.models.settings import CafeSettings
from app.models.table import Table
from app.models.user import User
from app.services.session_service import SessionService
from app.schemas.billing import (
    BillReceiptItem,
    BillReceiptResponse,
    GenerateBillRequest,
    InvoiceResponse,
    SettlePaymentRequest,
)
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/billing", tags=["Billing & POS"])


@router.get("/ledger", response_model=List[InvoiceResponse])
def get_billing_ledger(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all financial invoices with tax breakdown (Admin only)."""
    invoices = db.query(BillingInvoice).order_by(BillingInvoice.created_at.desc()).all()
    results = []
    for inv in invoices:
        order = db.query(Order).filter(Order.id == inv.order_id).first() if inv.order_id else None
        session = db.query(DiningSession).filter(DiningSession.id == inv.dining_session_id).first() if inv.dining_session_id else None
        table_id = order.table_id if order else (session.table_id if session else None)
        table_num = order.table_number if order else (session.table_number if session else None)
        cust_name = order.customer_name if order else (session.orders[0].customer_name if session and session.orders else "Guest")
        tbl = db.query(Table).filter(Table.id == table_id).first() if table_id else None

        results.append(
            InvoiceResponse(
                id=inv.id,
                order_id=inv.order_id,
                dining_session_id=inv.dining_session_id,
                bill_type=inv.bill_type,
                invoice_number=inv.invoice_number,
                table_number=table_num,
                customer_name=cust_name,
                subtotal=inv.subtotal,
                cgst_rate=inv.cgst_rate,
                cgst_amount=inv.cgst_amount,
                sgst_rate=inv.sgst_rate,
                sgst_amount=inv.sgst_amount,
                tax_amount=inv.tax_amount,
                discount_percentage=inv.discount_percentage,
                discount_amount=inv.discount_amount,
                total=inv.total,
                payment_method=inv.payment_method,
                payment_status=inv.payment_status,
                settled_at=inv.settled_at,
                created_at=inv.created_at,
                table_status=tbl.status if tbl else None,
            )
        )
    return results



def _format_session_receipt(session: DiningSession, invoice: Optional[BillingInvoice] = None) -> BillReceiptResponse:
    """Format consolidated bill receipt across all orders in a dining session."""
    valid_orders = [o for o in session.orders if o.status != OrderStatus.CANCELLED.value]
    
    # Consolidate items
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


@router.post("/sessions/{session_id}/generate", response_model=BillReceiptResponse)
async def generate_session_bill(
    session_id: str,
    payload: Optional[GenerateBillRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Generate final consolidated bill for a dining session.
    Releases physical table to AVAILABLE immediately.
    """
    disc_pct = payload.discount_percentage if payload else 0.0
    extra_chg = payload.extra_charge if payload else 0.0
    invoice, session = await SessionService.generate_final_bill(db, session_id, disc_pct, extra_charge=extra_chg)
    return _format_session_receipt(session, invoice)


@router.post("/sessions/{session_id}/settle", response_model=InvoiceResponse)
async def settle_session_bill(
    session_id: str,
    payload: SettlePaymentRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Settle final bill for dining session and close session.
    Guarantees table is NOT forced to AVAILABLE if another OPEN session is running.
    """
    invoice, session = await SessionService.settle_session_bill(db, session_id, payload.payment_method)
    tbl = db.query(Table).filter(Table.id == session.table_id).first()
    
    return InvoiceResponse(
        id=invoice.id,
        order_id=invoice.order_id,
        dining_session_id=session.id,
        bill_type=invoice.bill_type,
        invoice_number=invoice.invoice_number,
        table_number=session.table_number,
        customer_name=session.orders[0].customer_name if session.orders else "Guest",
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
        table_status=tbl.status if tbl else None,
    )


@router.get("/sessions/{session_id}", response_model=BillReceiptResponse)
def get_session_bill_receipt(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Get printable receipt for a dining session."""
    session = db.query(DiningSession).filter(DiningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dining session '{session_id}' not found",
        )
    invoice = (
        db.query(BillingInvoice)
        .filter(BillingInvoice.dining_session_id == session.id, BillingInvoice.bill_type == "SESSION")
        .first()
    )
    return _format_session_receipt(session, invoice)


@router.get("/pending", response_model=List[InvoiceResponse])
def get_pending_invoices(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all unpaid bills (PAYMENT_PENDING) independent of physical table occupancy."""
    invoices = (
        db.query(BillingInvoice)
        .filter(
            BillingInvoice.payment_status == "PENDING",
            BillingInvoice.bill_type == "SESSION",
        )
        .order_by(BillingInvoice.created_at.desc())
        .all()
    )
    tables = {t.id: t for t in db.query(Table).all()}
    
    results = []
    for inv in invoices:
        order = db.query(Order).filter(Order.id == inv.order_id).first() if inv.order_id else None
        session = db.query(DiningSession).filter(DiningSession.id == inv.dining_session_id).first() if inv.dining_session_id else None
        
        table_id = order.table_id if order else (session.table_id if session else None)
        table_num = order.table_number if order else (session.table_number if session else None)
        cust_name = order.customer_name if order else (session.orders[0].customer_name if session and session.orders else "Guest")
        
        tbl = tables.get(table_id)
        
        results.append(
            InvoiceResponse(
                id=inv.id,
                order_id=inv.order_id,
                dining_session_id=inv.dining_session_id,
                bill_type=inv.bill_type,
                invoice_number=inv.invoice_number,
                table_number=table_num,
                customer_name=cust_name,
                subtotal=inv.subtotal,
                cgst_rate=inv.cgst_rate,
                cgst_amount=inv.cgst_amount,
                sgst_rate=inv.sgst_rate,
                sgst_amount=inv.sgst_amount,
                tax_amount=inv.tax_amount,
                discount_percentage=inv.discount_percentage,
                discount_amount=inv.discount_amount,
                total=inv.total,
                payment_method=inv.payment_method,
                payment_status=inv.payment_status,
                settled_at=inv.settled_at,
                created_at=inv.created_at,
                table_status=tbl.status if tbl else None,
            )
        )
    return results


@router.get("/{order_id}", response_model=BillReceiptResponse)
def get_bill_receipt(order_id: str, db: Session = Depends(get_db)):
    """Retrieve full itemized bill receipt with GST breakdown and persisted discount for an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    invoice = db.query(BillingInvoice).filter(BillingInvoice.order_id == order_id).first()
    bill_number = invoice.invoice_number if invoice else f"BILL-{order.id}"

    # Build item receipt items
    items = []
    for oi in order.items:
        items.append(
            BillReceiptItem(
                name=oi.name,
                quantity=oi.quantity,
                unit_price=oi.unit_price,
                total_price=oi.item_total,
                notes=oi.special_instructions,
            )
        )

    tax_amt = order.tax
    cgst = round(tax_amt / 2, 2)
    sgst = round(tax_amt - cgst, 2)
    disc_pct = invoice.discount_percentage if invoice else (getattr(order, "discount_percentage", 0.0) or 0.0)
    disc_amt = invoice.discount_amount if invoice else (getattr(order, "discount_amount", 0.0) or 0.0)
    extra_chg = invoice.extra_charge if invoice else (getattr(order, "extra_charge", 0.0) or 0.0)

    return BillReceiptResponse(
        bill_number=bill_number,
        order_id=order.id,
        table_number=order.table_number or 0,
        customer_name=order.customer_name,
        customer_mobile=order.customer_mobile,
        special_instructions=order.special_instructions,
        items=items,
        subtotal=order.subtotal,
        cgst=cgst,
        sgst=sgst,
        tax_amount=tax_amt,
        discount_percentage=disc_pct,
        discount_amount=disc_amt,
        extra_charge=extra_chg,
        total=order.total,
        payment_status=order.payment_status,
        created_at=order.created_at.isoformat(),
        session_status=order.dining_session.status if order.dining_session else None,
        table_status=db.query(Table.status).filter(Table.id == order.table_id).scalar(),
    )


@router.post("/{order_id}/generate", response_model=BillReceiptResponse)
async def generate_bill(
    order_id: str,
    payload: Optional[GenerateBillRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Generate or recalculate official bill for an order with optional bill-level fixed discount (Admin only).
    Enforces validation: discount cannot be negative and cannot exceed eligible bill amount.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    # 1. Authoritative subtotal from persisted order items (No GST / taxes)
    subtotal = round(sum(oi.item_total for oi in order.items), 2)
    tax = 0.0
    cgst = 0.0
    sgst = 0.0

    # 2. Validate discount percentage (0 to 100%)
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

    # Server calculates authoritative discount amount from subtotal
    disc_amt = round(subtotal * (disc_pct / 100.0), 2)

    # 3. Final total calculation: Subtotal - Discount + Extra Charge
    final_total = max(0.0, round(subtotal - disc_amt + extra_chg, 2))

    # 4. Upsert BillingInvoice
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

    # 5. Persist on Order
    order.subtotal = subtotal
    order.tax = tax
    order.discount_percentage = disc_pct
    order.discount_amount = disc_amt
    order.extra_charge = extra_chg
    order.total = final_total
    order.updated_at = datetime.now(timezone.utc)

    # 6. Close current dining session for new orders (BILL_GENERATED) & release table
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

    # Build receipt items
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


@router.post("/{order_id}/settle", response_model=InvoiceResponse)
async def settle_bill_payment(
    order_id: str,
    payload: SettlePaymentRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Settle order payment (Admin only).
    Marks invoice & order PAID, releases table to AVAILABLE if all orders are settled.
    Broadcasts PAYMENT_SETTLED.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    invoice = db.query(BillingInvoice).filter(BillingInvoice.order_id == order_id).first()
    if not invoice:
        # Create invoice if missing
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

    # Close dining session if all orders settled
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

    # Check if table has an active OPEN session! If yes, table remains OCCUPIED!
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

    # Broadcast real-time payment settlement
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

