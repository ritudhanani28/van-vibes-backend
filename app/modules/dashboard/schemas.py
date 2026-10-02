from typing import List
from pydantic import BaseModel, ConfigDict, Field

from app.modules.orders.schemas import OrderResponse


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    total_orders: int = Field(..., alias="totalOrders")
    kitchen_pending: int = Field(..., alias="kitchenPending")
    occupied_tables: int = Field(..., alias="occupiedTables")
    total_tables: int = Field(12, alias="totalTables")
    settled_revenue: float = Field(..., alias="settledRevenue")
    recent_orders: List[OrderResponse] = Field([], alias="recentOrders")


class KitchenSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    incoming_orders: int = Field(..., alias="incomingOrders")
    active_prep: int = Field(..., alias="activePrep")
    completed_today: int = Field(..., alias="completedToday")
