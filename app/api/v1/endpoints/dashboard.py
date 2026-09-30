from datetime import datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin, require_chef_or_admin
from app.db.session import get_db
from app.models.billing import BillingInvoice
from app.models.order import Order
from app.models.table import Table
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryResponse, KitchenSummaryResponse
from app.schemas.order import OrderResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

IST = ZoneInfo("Asia/Kolkata")


def parse_date_range(range_param: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    if not range_param or range_param.lower().strip() in ("all", "none"):
        return None, None

    now_ist = datetime.now(IST)
    r = range_param.lower().strip().replace(" ", "_")

    if r == "today":
        start = datetime.combine(now_ist.date(), time.min, tzinfo=IST)
        end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
    elif r == "yesterday":
        y_date = now_ist.date() - timedelta(days=1)
        start = datetime.combine(y_date, time.min, tzinfo=IST)
        end = datetime.combine(y_date, time.max, tzinfo=IST)
    elif r in ("30_days", "last_30_days"):
        s_date = (now_ist - timedelta(days=30)).date()
        start = datetime.combine(s_date, time.min, tzinfo=IST)
        end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
    elif r in ("month", "this_month"):
        s_date = now_ist.date().replace(day=1)
        start = datetime.combine(s_date, time.min, tzinfo=IST)
        end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
    elif r in ("year", "this_year"):
        s_date = now_ist.date().replace(month=1, day=1)
        start = datetime.combine(s_date, time.min, tzinfo=IST)
        end = datetime.combine(now_ist.date(), time.max, tzinfo=IST)
    else:
        return None, None

    return start, end


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    range: Optional[str] = Query(None, description="Date range: today, yesterday, 30_days, month, year, all"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Live aggregated KPI metrics for the Admin Dashboard.
    Calculated authoritatively from SQL database with backend date range filtering.
    """
    start_dt, end_dt = parse_date_range(range)

    order_query = db.query(Order)
    invoice_query = db.query(BillingInvoice)

    if start_dt and end_dt:
        order_query = order_query.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        invoice_query = invoice_query.filter(
            BillingInvoice.created_at >= start_dt, BillingInvoice.created_at <= end_dt
        )

    total_orders = order_query.with_entities(func.count(Order.id)).scalar() or 0

    kitchen_pending = (
        order_query.filter(Order.status.in_(["ORDER_PLACED", "ACCEPTED", "PREPARING"]))
        .with_entities(func.count(Order.id))
        .scalar()
        or 0
    )

    occupied_tables = (
        db.query(func.count(Table.id))
        .filter(Table.status == "OCCUPIED", Table.is_active == True)
        .scalar()
        or 0
    )
    total_tables = (
        db.query(func.count(Table.id)).filter(Table.is_active == True).scalar() or 12
    )

    # Settled revenue from paid invoices / paid orders
    settled_revenue = (
        invoice_query.filter(BillingInvoice.payment_status == "PAID")
        .with_entities(func.sum(BillingInvoice.total))
        .scalar()
        or 0.0
    )

    recent_orders_db = (
        order_query.order_by(Order.created_at.desc()).limit(10).all()
    )
    recent_orders = [OrderResponse.model_validate(o) for o in recent_orders_db]

    return DashboardSummaryResponse(
        total_orders=total_orders,
        kitchen_pending=kitchen_pending,
        occupied_tables=occupied_tables,
        total_tables=total_tables,
        settled_revenue=round(float(settled_revenue), 2),
        recent_orders=recent_orders,
    )


@router.get("/kitchen", response_model=KitchenSummaryResponse)
def get_kitchen_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
):
    """Kitchen display operational counts for Chef."""
    incoming = (
        db.query(func.count(Order.id))
        .filter(Order.status == "ORDER_PLACED")
        .scalar()
        or 0
    )
    active_prep = (
        db.query(func.count(Order.id))
        .filter(Order.status.in_(["ACCEPTED", "PREPARING"]))
        .scalar()
        or 0
    )
    completed_today = (
        db.query(func.count(Order.id))
        .filter(Order.status.in_(["READY", "SERVED", "COMPLETED"]))
        .scalar()
        or 0
    )

    return KitchenSummaryResponse(
        incoming_orders=incoming,
        active_prep=active_prep,
        completed_today=completed_today,
    )
