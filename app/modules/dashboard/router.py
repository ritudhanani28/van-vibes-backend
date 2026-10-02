from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.core.dependencies import require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.dashboard.apis import get_dashboard_summary_endpoint, get_kitchen_summary_endpoint
from app.modules.dashboard.schemas import DashboardSummaryResponse, KitchenSummaryResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

router.add_api_route(
    "/summary",
    get_dashboard_summary_endpoint,
    methods=["GET"],
    response_model=DashboardSummaryResponse,
    summary="Get Dashboard KPI Summary",
)

router.add_api_route(
    "/kitchen",
    get_kitchen_summary_endpoint,
    methods=["GET"],
    response_model=KitchenSummaryResponse,
    summary="Get Kitchen Summary Metrics",
)
