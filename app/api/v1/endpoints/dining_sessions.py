from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_chef_or_admin
from app.db.session import get_db
from app.models.billing import BillingInvoice
from app.models.dining_session import DiningSession, SessionStatus
from app.models.order import Order, OrderStatus
from app.models.table import Table
from app.models.user import User
from app.schemas.dining_session import (
    DiningSessionDetailResponse,
    DiningSessionResponse,
    GenerateSessionBillRequest,
    SettleSessionBillRequest,
)
from app.schemas.billing import BillReceiptResponse, InvoiceResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/dining-sessions", tags=["Dining Sessions"])


def _format_session(s: DiningSession, tbl_status: Optional[str] = None) -> DiningSessionResponse:
    valid_orders = [o for o in s.orders if o.status != OrderStatus.CANCELLED.value] if s.orders else []
    total_amt = sum(o.total for o in valid_orders) if valid_orders else 0.0
    
    # Check if all valid orders are paid
    all_orders_paid = len(valid_orders) > 0 and all(o.payment_status == "PAID" for o in valid_orders)

    # Find authoritative session invoice if generated
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


@router.get("", response_model=List[DiningSessionResponse])
def list_dining_sessions(
    status: Optional[str] = Query(None, description="Filter by session status: OPEN, BILL_GENERATED, CLOSED"),
    table_id: Optional[str] = Query(None, description="Filter by table ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
):
    """List dining sessions with optional table and status filtering."""
    query = db.query(DiningSession).order_by(DiningSession.created_at.desc())
    if status:
        query = query.filter(DiningSession.status == status)
    if table_id:
        query = query.filter(DiningSession.table_id == table_id)
    
    sessions = query.limit(100).all()
    
    # Pre-fetch table statuses
    tables = {t.id: t.status for t in db.query(Table).all()}
    return [_format_session(s, tables.get(s.table_id)) for s in sessions]


@router.get("/{session_id}", response_model=DiningSessionDetailResponse)
def get_dining_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Get full details of a single dining session including orders and invoice."""
    s = db.query(DiningSession).filter(DiningSession.id == session_id).first()
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
    disc_pct = 0.0
    disc_amt = 0.0
    tax_amt = round(subtotal * 0.05, 2)
    final_total = round(subtotal + tax_amt, 2)
    payment_st = "PENDING"

    if inv:
        disc_pct = inv.discount_percentage
        disc_amt = inv.discount_amount
        tax_amt = inv.tax_amount
        final_total = inv.total
        payment_st = inv.payment_status
        invoice_data = {
            "id": inv.id,
            "invoiceNumber": inv.invoice_number,
            "subtotal": inv.subtotal,
            "taxAmount": inv.tax_amount,
            "discountPercentage": inv.discount_percentage,
            "discountAmount": inv.discount_amount,
            "total": inv.total,
            "paymentMethod": inv.payment_method,
            "paymentStatus": inv.payment_status,
            "settledAt": inv.settled_at.isoformat() if inv.settled_at else None,
            "createdAt": inv.created_at.isoformat(),
        }

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
        tax=round(tax_amt, 2),
        discount_percentage=disc_pct,
        discount_amount=disc_amt,
        total=final_total,
    )


@router.post("/table/{table_id}/start", response_model=DiningSessionResponse)
async def start_dining_session_for_table(
    table_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
):
    """Admin endpoint to explicitly start or get active dining session for a table."""
    sess, _ = await SessionService.get_or_create_active_session(db, table_id)
    tbl = db.query(Table).filter(Table.id == table_id).first()
    return _format_session(sess, tbl.status if tbl else None)
