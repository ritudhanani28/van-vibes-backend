from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.orders.models import Order
from app.modules.sessions.models import BillingInvoice
from app.modules.tables.models import Table


class DashboardCRUD:
    @staticmethod
    def get_summary_metrics(
        db: Session,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
    ) -> Tuple[int, int, int, int, float, list]:
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

        settled_revenue = (
            invoice_query.filter(BillingInvoice.payment_status == "PAID")
            .with_entities(func.sum(BillingInvoice.total))
            .scalar()
            or 0.0
        )

        recent_orders_db = order_query.order_by(Order.created_at.desc()).limit(10).all()

        return (
            total_orders,
            kitchen_pending,
            occupied_tables,
            total_tables,
            round(float(settled_revenue), 2),
            recent_orders_db,
        )

    @staticmethod
    def get_kitchen_metrics(db: Session) -> Tuple[int, int, int]:
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
        return incoming, active_prep, completed_today
