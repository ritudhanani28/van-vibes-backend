from typing import Optional
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.dashboard.schemas import DashboardSummaryResponse, KitchenSummaryResponse
from app.modules.dashboard.service import DashboardService


def get_dashboard_summary_endpoint(
    range: Optional[str] = Query(None, description="Date range: today, yesterday, 30_days, month, year, all"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DashboardSummaryResponse:
    """Live aggregated KPI metrics for the Admin Dashboard."""
    return DashboardService.get_summary(db, range)


def get_kitchen_summary_endpoint(
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
) -> KitchenSummaryResponse:
    """Kitchen display operational counts for Chef."""
    return DashboardService.get_kitchen_summary(db)
