from datetime import datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.modules.dashboard.crud import DashboardCRUD
from app.modules.dashboard.schemas import DashboardSummaryResponse, KitchenSummaryResponse
from app.modules.orders.schemas import OrderResponse

IST = ZoneInfo("Asia/Kolkata")


class DashboardService:
    @staticmethod
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

    @classmethod
    def get_summary(cls, db: Session, range_param: Optional[str] = None) -> DashboardSummaryResponse:
        start_dt, end_dt = cls.parse_date_range(range_param)
        (
            total_orders,
            kitchen_pending,
            occupied_tables,
            total_tables,
            settled_revenue,
            recent_orders_db,
        ) = DashboardCRUD.get_summary_metrics(db, start_dt, end_dt)

        recent_orders = [OrderResponse.model_validate(o) for o in recent_orders_db]

        return DashboardSummaryResponse(
            total_orders=total_orders,
            kitchen_pending=kitchen_pending,
            occupied_tables=occupied_tables,
            total_tables=total_tables,
            settled_revenue=settled_revenue,
            recent_orders=recent_orders,
        )

    @classmethod
    def get_kitchen_summary(cls, db: Session) -> KitchenSummaryResponse:
        incoming, active_prep, completed_today = DashboardCRUD.get_kitchen_metrics(db)
        return KitchenSummaryResponse(
            incoming_orders=incoming,
            active_prep=active_prep,
            completed_today=completed_today,
        )

parse_date_range = DashboardService.parse_date_range
