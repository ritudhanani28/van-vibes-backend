from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GenerateBillRequest(BaseModel):
    discount_percentage: Optional[float] = Field(None, alias="discountPercentage")
    discount_amount: Optional[float] = Field(None, alias="discountAmount")

    class Config:
        populate_by_name = True


class InvoiceResponse(BaseModel):
    id: str
    order_id: Optional[str] = Field(None, alias="orderId")
    dining_session_id: Optional[str] = Field(None, alias="diningSessionId")
    bill_type: str = Field("SESSION", alias="billType")
    table_status: Optional[str] = Field(None, alias="tableStatus")
    invoice_number: str = Field(..., alias="invoiceNumber")
    table_number: Optional[int] = Field(None, alias="tableNumber")
    customer_name: Optional[str] = Field(None, alias="customerName")
    subtotal: float
    cgst_rate: float = Field(0.025, alias="cgstRate")
    cgst_amount: float = Field(..., alias="cgstAmount")
    sgst_rate: float = Field(0.025, alias="sgstRate")
    sgst_amount: float = Field(..., alias="sgstAmount")
    tax_amount: float = Field(..., alias="taxAmount")
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    total: float
    payment_method: str = Field("CASH", alias="paymentMethod")
    payment_status: str = Field("PENDING", alias="paymentStatus")
    settled_at: Optional[datetime] = Field(None, alias="settledAt")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True
        from_attributes = True


class SettlePaymentRequest(BaseModel):
    payment_method: str = Field("CASH", alias="paymentMethod")  # CASH, UPI, CARD


class BillReceiptItem(BaseModel):
    name: str
    quantity: int
    unit_price: float = Field(..., alias="unitPrice")
    total_price: float = Field(..., alias="totalPrice")
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class BillReceiptResponse(BaseModel):
    bill_number: str = Field(..., alias="billNumber")
    order_id: Optional[str] = Field(None, alias="orderId")
    dining_session_id: Optional[str] = Field(None, alias="diningSessionId")
    order_ids: List[str] = Field(default_factory=list, alias="orderIds")
    table_number: int = Field(..., alias="tableNumber")
    customer_name: str = Field(..., alias="customerName")
    customer_mobile: str = Field(..., alias="customerMobile")
    special_instructions: Optional[str] = Field(None, alias="specialInstructions")
    items: List[BillReceiptItem]
    subtotal: float
    cgst: float
    sgst: float
    tax_amount: float = Field(..., alias="taxAmount")
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    total: float
    payment_status: str = Field(..., alias="paymentStatus")
    created_at: str = Field(..., alias="createdAt")
    session_status: Optional[str] = Field(None, alias="sessionStatus")
    table_status: Optional[str] = Field(None, alias="tableStatus")

    class Config:
        populate_by_name = True
