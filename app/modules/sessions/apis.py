from datetime import datetime, timezone
from typing import List, Optional
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.menu.models import MenuItem
from app.modules.orders.models import Order, OrderStatus
from app.modules.sessions.crud import BillingCRUD, SessionCRUD
from app.modules.sessions.models import BillingInvoice, DiningSession, SessionStatus
from app.modules.sessions.schemas import (
    BillReceiptItem,
    BillReceiptResponse,
    IncompleteItemDetail,
    IncompleteOrderItemResponse,
    DiningSessionDetailResponse,
    DiningSessionResponse,
    GenerateBillRequest,
    InvoiceResponse,
    SettlePaymentRequest,
)
from app.modules.sessions.service import BillingService, SessionService, calculate_bill_totals
from app.modules.tables.models import Table
from app.modules.settings.models import CafeSettings
from app.modules.notifications.manager import ws_manager


def _format_session(s: DiningSession, tbl_status: Optional[str] = None) -> DiningSessionResponse:
    valid_orders = [o for o in s.orders if o.status != OrderStatus.CANCELLED.value] if s.orders else []
    total_amt = sum(o.total for o in valid_orders) if valid_orders else 0.0

    all_orders_paid = len(valid_orders) > 0 and all(o.payment_status == "PAID" for o in valid_orders)

    session_inv = next((i for i in s.invoices if i.bill_type == "SESSION"), None)
    if session_inv:
        total_amt = session_inv.total
        payment_st = session_inv.payment_status
    elif all_orders_paid:
        payment_st = "PAID"
    else:
        payment_st = "PAID" if s.status == SessionStatus.CLOSED.value else "PENDING"

    effective_status = s.status
    if all_orders_paid or (session_inv and session_inv.payment_status == "PAID"):
        effective_status = SessionStatus.CLOSED.value

    return DiningSessionResponse(
        id=s.id,
        table_id=s.table_id,
        table_number=s.table_number,
        status=effective_status,
        created_at=s.created_at,
        updated_at=s.updated_at,
        closed_at=s.closed_at,
        order_count=len(s.orders) if s.orders else 0,
        total_amount=round(total_amt, 2),
        payment_status=payment_st,
        table_status=tbl_status or (s.table.status if s.table else None),
    )


# Dining Sessions Endpoints
def list_dining_sessions_endpoint(
    status: Optional[str] = Query(None, description="Filter by session status: OPEN, BILL_GENERATED, CLOSED"),
    table_id: Optional[str] = Query(None, description="Filter by table ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
):
    sessions = SessionCRUD.get_multi(db, status=status, table_id=table_id)
    tables = {t.id: t.status for t in db.query(Table).all()}
    return [_format_session(s, tables.get(s.table_id)) for s in sessions]


def get_dining_session_detail_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
):
    s = SessionCRUD.get_by_id(db, session_id)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dining session '{session_id}' not found",
        )

    orders_data = []
    valid_orders = [o for o in s.orders if o.status != OrderStatus.CANCELLED.value]
    subtotal = sum(o.subtotal for o in valid_orders)

    for o in s.orders:
        orders_data.append({
            "id": o.id,
            "tableId": o.table_id,
            "tableNumber": o.table_number,
            "customerName": o.customer_name,
            "customerMobile": o.customer_mobile,
            "status": o.status,
            "paymentStatus": o.payment_status,
            "subtotal": o.subtotal,
            "tax": o.tax,
            "discountAmount": o.discount_amount,
            "total": o.total,
            "createdAt": o.created_at.isoformat(),
            "items": [
                {
                    "id": it.id,
                    "name": it.name,
                    "quantity": it.quantity,
                    "unitPrice": it.unit_price,
                    "itemTotal": it.item_total,
                    "selectedOptions": it.selected_options,
                    "selectedAddOns": it.selected_add_ons,
                    "specialInstructions": it.special_instructions,
                }
                for it in o.items
            ]
        })

    invoice_data = None
    inv = next((i for i in s.invoices if i.bill_type == "SESSION"), None)
    payment_st = "PENDING"

    if inv:
        disc_pct = inv.discount_percentage
        disc_amt = inv.discount_amount
        extra_chg = inv.extra_charge
        round_off = getattr(inv, "round_off", 0.0)
        final_total = inv.total
        amount_after_adjustments = round(inv.subtotal - disc_amt + extra_chg, 2)
        payment_st = inv.payment_status
        invoice_data = {
            "id": inv.id,
            "invoiceNumber": inv.invoice_number,
            "subtotal": inv.subtotal,
            "taxAmount": 0.0,
            "discountPercentage": inv.discount_percentage,
            "discountAmount": inv.discount_amount,
            "extraCharge": inv.extra_charge,
            "amountAfterAdjustments": amount_after_adjustments,
            "roundOff": round_off,
            "total": inv.total,
            "paymentMethod": inv.payment_method,
            "paymentStatus": inv.payment_status,
            "settledAt": inv.settled_at.isoformat() if inv.settled_at else None,
            "createdAt": inv.created_at.isoformat(),
        }
    else:
        calc = calculate_bill_totals(subtotal, 0.0, 0.0)
        disc_pct = 0.0
        disc_amt = 0.0
        extra_chg = 0.0
        amount_after_adjustments = calc["amount_after_adjustments"]
        round_off = calc["round_off"]
        final_total = calc["total"]

    tbl = db.query(Table).filter(Table.id == s.table_id).first()

    return DiningSessionDetailResponse(
        id=s.id,
        table_id=s.table_id,
        table_number=s.table_number,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
        closed_at=s.closed_at,
        order_count=len(s.orders),
        total_amount=final_total,
        payment_status=payment_st,
        table_status=tbl.status if tbl else None,
        orders=orders_data,
        invoice=invoice_data,
        subtotal=round(subtotal, 2),
        tax=0.0,
        discount_percentage=disc_pct,
        discount_amount=disc_amt,
        extra_charge=extra_chg,
        amount_after_adjustments=amount_after_adjustments,
        round_off=round_off,
        total=final_total,
    )


async def start_dining_session_for_table_endpoint(
    table_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
):
    sess, _ = await SessionService.get_or_create_active_session(db, table_id)
    tbl = db.query(Table).filter(Table.id == table_id).first()
    return _format_session(sess, tbl.status if tbl else None)


# Billing Endpoints
def get_billing_ledger_endpoint(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    invoices = BillingCRUD.get_ledger(db)
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
                tax_amount=0.0,
                discount_percentage=inv.discount_percentage,
                discount_amount=inv.discount_amount,
                extra_charge=getattr(inv, "extra_charge", 0.0),
                round_off=getattr(inv, "round_off", 0.0),
                total=inv.total,
                payment_method=inv.payment_method,
                payment_status=inv.payment_status,
                settled_at=inv.settled_at,
                created_at=inv.created_at,
                table_status=tbl.status if tbl else None,
            )
        )
    return results


async def generate_bill_endpoint(
    order_id: str,
    payload: Optional[GenerateBillRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await BillingService.generate_order_bill(db=db, order_id=order_id, payload=payload)


async def settle_bill_payment_endpoint(
    order_id: str,
    payload: SettlePaymentRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await BillingService.settle_order_payment(db=db, order_id=order_id, payload=payload)

# Aliases for backward compatibility
generate_bill = generate_bill_endpoint
settle_bill_payment = settle_bill_payment_endpoint


async def generate_session_bill_endpoint(
    session_id: str,
    payload: Optional[GenerateBillRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    disc_pct = payload.discount_percentage if payload else 0.0
    extra_chg = payload.extra_charge if payload else 0.0
    invoice, session = await SessionService.generate_final_bill(db, session_id, disc_pct, extra_charge=extra_chg)
    return BillingService.format_session_receipt(session, invoice, db)


async def settle_session_bill_endpoint(
    session_id: str,
    payload: Optional[SettlePaymentRequest] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    pay_method = payload.payment_method if payload else "CASH"
    invoice, session = await SessionService.settle_session_bill(db, session_id, payment_method=pay_method)
    tbl = db.query(Table).filter(Table.id == session.table_id).first()
    return InvoiceResponse(
        id=invoice.id,
        order_id=invoice.order_id,
        dining_session_id=invoice.dining_session_id,
        bill_type=invoice.bill_type,
        invoice_number=invoice.invoice_number,
        table_number=session.table_number,
        customer_name=session.orders[0].customer_name if session.orders else "Guest",
        subtotal=invoice.subtotal,
        cgst_rate=invoice.cgst_rate,
        cgst_amount=invoice.cgst_amount,
        sgst_rate=invoice.sgst_rate,
        sgst_amount=invoice.sgst_amount,
        tax_amount=0.0,
        discount_percentage=invoice.discount_percentage,
        discount_amount=invoice.discount_amount,
        extra_charge=invoice.extra_charge,
        round_off=getattr(invoice, "round_off", 0.0),
        total=invoice.total,
        payment_method=invoice.payment_method,
        payment_status=invoice.payment_status,
        settled_at=invoice.settled_at,
        created_at=invoice.created_at,
        table_status=tbl.status if tbl else None,
    )


def get_session_bill_receipt_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
) -> BillReceiptResponse:
    """Get printable receipt for a dining session."""
    session = SessionCRUD.get_by_id(db, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dining session '{session_id}' not found",
        )
    invoice = BillingCRUD.get_invoice_by_session(db, session.id, bill_type="SESSION")
    return BillingService.format_session_receipt(session, invoice, db)


def get_pending_invoices_endpoint(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> List[InvoiceResponse]:
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
                tax_amount=0.0,
                discount_percentage=inv.discount_percentage,
                discount_amount=inv.discount_amount,
                extra_charge=getattr(inv, "extra_charge", 0.0),
                round_off=getattr(inv, "round_off", 0.0),
                total=inv.total,
                payment_method=inv.payment_method,
                payment_status=inv.payment_status,
                settled_at=inv.settled_at,
                created_at=inv.created_at,
                table_status=tbl.status if tbl else None,
            )
        )
    return results


def get_bill_receipt_endpoint(order_id: str, db: Session = Depends(get_db)) -> BillReceiptResponse:
    """Retrieve full itemized bill receipt with GST breakdown and persisted discount for an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    invoice = db.query(BillingInvoice).filter(BillingInvoice.order_id == order_id).first()
    bill_number = invoice.invoice_number if invoice else f"BILL-{order.id}"

    menu_item_ids = {oi.menu_item_id for oi in order.items if getattr(oi, "menu_item_id", None)}
    menu_items_map = {}
    if menu_item_ids:
        menu_items = db.query(MenuItem).filter(MenuItem.id.in_(menu_item_ids)).all()
        menu_items_map = {m.id: m for m in menu_items}

    items = []
    for oi in order.items:
        base_unit, base_tot, extras = BillingService._extract_item_extras_and_base_price(oi, menu_items_map)
        items.append(
            BillReceiptItem(
                name=oi.name,
                quantity=oi.quantity,
                unit_price=oi.unit_price,
                total_price=oi.item_total,
                base_unit_price=base_unit,
                base_total_price=base_tot,
                notes=oi.special_instructions,
                extras=extras,
            )
        )

    tax_amt = 0.0
    cgst = 0.0
    sgst = 0.0
    disc_pct = invoice.discount_percentage if invoice else (getattr(order, "discount_percentage", 0.0) or 0.0)
    disc_amt = invoice.discount_amount if invoice else (getattr(order, "discount_amount", 0.0) or 0.0)
    extra_chg = invoice.extra_charge if invoice else (getattr(order, "extra_charge", 0.0) or 0.0)
    round_off = getattr(invoice, "round_off", 0.0) if invoice else getattr(order, "round_off", 0.0)
    amount_after_adjustments = round(order.subtotal - disc_amt + extra_chg, 2)

    COMPLETED_STATUSES = {OrderStatus.COMPLETED.value, OrderStatus.SERVED.value}
    incomplete_list = []
    if order.dining_session_id:
        sess = SessionCRUD.get_by_id(db, order.dining_session_id)
        if sess:
            valid_orders = [o for o in sess.orders if o.status != OrderStatus.CANCELLED.value]
            incomplete_list = [
                IncompleteOrderItemResponse(
                    order_id=o.id,
                    order_number=o.id,
                    table_number=sess.table_number or (o.table_number or 0),
                    status=o.status,
                    items=[
                        IncompleteItemDetail(name=oi.name, quantity=oi.quantity)
                        for oi in o.items
                    ],
                )
                for o in valid_orders
                if o.status not in COMPLETED_STATUSES
            ]
    elif order.status not in COMPLETED_STATUSES and order.status != OrderStatus.CANCELLED.value:
        incomplete_list = [
            IncompleteOrderItemResponse(
                order_id=order.id,
                order_number=order.id,
                table_number=order.table_number or 0,
                status=order.status,
                items=[
                    IncompleteItemDetail(name=oi.name, quantity=oi.quantity)
                    for oi in order.items
                ],
            )
        ]

    cafe_settings = db.query(CafeSettings).first()
    return BillReceiptResponse(
        bill_number=bill_number,
        upi_id=cafe_settings.upi_id if (cafe_settings and cafe_settings.upi_id) else "9773291261@okbizaxis",
        upi_payee_name=cafe_settings.upi_payee_name if (cafe_settings and cafe_settings.upi_payee_name) else "OM DIYORA",
        payment_qr_code=cafe_settings.payment_qr_code if (cafe_settings and cafe_settings.payment_qr_code) else None,
        order_id=order.id,
        table_number=order.table_number or 0,
        customer_name=order.customer_name,
        customer_mobile=order.customer_mobile,
        special_instructions=order.special_instructions,
        items=items,
        subtotal=order.subtotal,
        cgst=0.0,
        sgst=0.0,
        tax_amount=0.0,
        discount_percentage=disc_pct,
        discount_amount=disc_amt,
        extra_charge=extra_chg,
        amount_after_adjustments=amount_after_adjustments,
        round_off=round_off,
        total=order.total,
        payment_status=order.payment_status,
        created_at=order.created_at.isoformat(),
        session_status=order.dining_session.status if order.dining_session else None,
        table_status=db.query(Table.status).filter(Table.id == order.table_id).scalar(),
        has_incomplete_orders=len(incomplete_list) > 0,
        incomplete_orders=incomplete_list,
    )
