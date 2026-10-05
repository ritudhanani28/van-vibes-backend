import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.modules.orders.models import OrderStatus


class CartItemInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    menu_item_id: str = Field(..., alias="menuItemId")
    name: str
    category: Optional[str] = None
    price: Optional[float] = 0.0
    quantity: int = Field(1, ge=1)
    selected_options: Optional[Dict[str, Any]] = Field(None, alias="selectedOptions")
    selected_add_ons: Optional[List[str]] = Field(None, alias="selectedAddOns")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_id: str = Field(..., alias="tableId")
    token: str
    session_token: str = Field(..., alias="sessionToken")
    customer_name: str = Field(..., alias="customerName", min_length=2, max_length=100)
    customer_mobile: str = Field(..., alias="customerMobile", min_length=10, max_length=10, pattern=r"^\d{10}$")

    @field_validator("customer_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("Please enter your full name (minimum 2 characters)")
        return s

    @field_validator("customer_mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        s = v.strip()
        if not re.match(r"^\d{10}$", s):
            raise ValueError("Phone number must contain exactly 10 digits")
        return s
    dining_session_id: Optional[str] = Field(None, alias="diningSessionId")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")
    items: List[CartItemInput] = Field(..., min_length=1)


class OrderItemResponse(BaseModel):
    """Full order item details with pricing for Admin and Customer invoice."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    menu_item_id: Optional[str] = Field(None, alias="menuItemId")
    name: str
    category: Optional[str] = None
    unit_price: float = Field(..., alias="unitPrice")
    quantity: int
    item_total: float = Field(..., alias="itemTotal")
    selected_options: Optional[Dict[str, Any]] = Field(None, alias="selectedOptions")
    selected_add_ons: Optional[List[str]] = Field(None, alias="selectedAddOns")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")

    @computed_field
    @property
    def item_name(self) -> str:
        return self.name

    @computed_field
    @property
    def price(self) -> float:
        return self.unit_price

    @computed_field
    @property
    def line_total(self) -> float:
        return self.item_total

    @computed_field
    @property
    def lineTotal(self) -> float:
        return self.item_total


class ChefOrderItemResponse(BaseModel):
    """Strictly sanitized item view for Kitchen/Chef. Absolutely NO prices or totals."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    menu_item_id: Optional[str] = Field(None, alias="menuItemId")
    name: str
    category: Optional[str] = None
    quantity: int
    selected_options: Optional[Dict[str, Any]] = Field(None, alias="selectedOptions")
    selected_add_ons: Optional[List[str]] = Field(None, alias="selectedAddOns")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")


class OrderResponse(BaseModel):
    """Full order details with financial breakdown for Admin and Billing."""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    cafe_id: str = Field("van-vibes", alias="cafeId")
    table_id: Optional[str] = Field(None, alias="tableId")
    table_number: Optional[int] = Field(None, alias="tableNumber")
    dining_session_id: Optional[str] = Field(None, alias="diningSessionId")
    session_token: str = Field(..., alias="sessionToken")
    customer_name: str = Field(..., alias="customerName")
    customer_mobile: str = Field(..., alias="customerMobile")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")
    status: str
    payment_status: str = Field(..., alias="paymentStatus")
    subtotal: float
    tax: float
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    total: float
    session_status: Optional[str] = Field(None, alias="sessionStatus")
    bill_generated: bool = Field(False, alias="billGenerated")
    activity_status: str = Field("ACTIVE", alias="activityStatus")
    is_active: bool = Field(True, alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    items: List[OrderItemResponse] = []


AdminOrderResponse = OrderResponse
AdminOrderItemResponse = OrderItemResponse


class ChefOrderResponse(BaseModel):
    """Strictly sanitized order view for kitchen staff (No prices, subtotals, taxes, discounts, or payments)"""
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    cafe_id: str = Field("van-vibes", alias="cafeId")
    table_id: Optional[str] = Field(None, alias="tableId")
    table_number: Optional[int] = Field(None, alias="tableNumber")
    customer_name: str = Field(..., alias="customerName")
    customer_mobile: str = Field(..., alias="customerMobile")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")
    status: str
    session_status: Optional[str] = Field(None, alias="sessionStatus")
    bill_generated: bool = Field(False, alias="billGenerated")
    activity_status: str = Field("ACTIVE", alias="activityStatus")
    is_active: bool = Field(True, alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    items: List[ChefOrderItemResponse] = []


class UpdateOrderStatusRequest(BaseModel):
    status: str


class CancelOrderRequest(BaseModel):
    reason: Optional[str] = None
