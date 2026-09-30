from typing import List
from pydantic import BaseModel, Field

from app.schemas.order import OrderResponse


class DashboardSummaryResponse(BaseModel):
    total_orders: int = Field(..., alias="totalOrders")
    kitchen_pending: int = Field(..., alias="kitchenPending")
    occupied_tables: int = Field(..., alias="occupiedTables")
    total_tables: int = Field(12, alias="totalTables")
    settled_revenue: float = Field(..., alias="settledRevenue")
    recent_orders: List[OrderResponse] = Field([], alias="recentOrders")

    class Config:
        populate_by_name = True


class KitchenSummaryResponse(BaseModel):
    incoming_orders: int = Field(..., alias="incomingOrders")
    active_prep: int = Field(..., alias="activePrep")
    completed_today: int = Field(..., alias="completedToday")

    class Config:
        populate_by_name = True
