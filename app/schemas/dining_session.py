from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DiningSessionResponse(BaseModel):
    id: str
    table_id: str = Field(..., alias="tableId")
    table_number: int = Field(..., alias="tableNumber")
    status: str  # OPEN, BILL_GENERATED, CLOSED
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    closed_at: Optional[datetime] = Field(None, alias="closedAt")
    order_count: int = Field(0, alias="orderCount")
    total_amount: float = Field(0.0, alias="totalAmount")
    payment_status: str = Field("PENDING", alias="paymentStatus")
    table_status: Optional[str] = Field(None, alias="tableStatus")

    class Config:
        populate_by_name = True
        from_attributes = True


class DiningSessionDetailResponse(DiningSessionResponse):
    orders: List[Dict[str, Any]] = Field(default_factory=list)
    invoice: Optional[Dict[str, Any]] = None
    subtotal: float = 0.0
    tax: float = 0.0
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    total: float = 0.0


class GenerateSessionBillRequest(BaseModel):
    discount_percentage: Optional[float] = Field(0.0, alias="discountPercentage", ge=0.0, le=100.0)

    class Config:
        populate_by_name = True


class SettleSessionBillRequest(BaseModel):
    payment_method: str = Field("CASH", alias="paymentMethod")  # CASH, UPI, CARD

    class Config:
        populate_by_name = True
