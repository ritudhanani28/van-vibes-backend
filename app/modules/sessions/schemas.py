from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GenerateBillRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    discount_percentage: Optional[float] = Field(None, alias="discountPercentage")
    discount_amount: Optional[float] = Field(None, alias="discountAmount")
    extra_charge: Optional[float] = Field(0.0, alias="extraCharge")


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    order_id: Optional[str] = Field(None, alias="orderId")
    dining_session_id: Optional[str] = Field(None, alias="diningSessionId")
    bill_type: str = Field("SESSION", alias="billType")
    table_status: Optional[str] = Field(None, alias="tableStatus")
    invoice_number: str = Field(..., alias="invoiceNumber")
    table_number: Optional[int] = Field(None, alias="tableNumber")
    customer_name: Optional[str] = Field(None, alias="customerName")
    subtotal: float
    cgst_rate: float = Field(0.0, alias="cgstRate")
    cgst_amount: float = Field(0.0, alias="cgstAmount")
    sgst_rate: float = Field(0.0, alias="sgstRate")
    sgst_amount: float = Field(0.0, alias="sgstAmount")
    tax_amount: float = Field(0.0, alias="taxAmount")
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    extra_charge: float = Field(0.0, alias="extraCharge")
    round_off: float = Field(0.0, alias="roundOff")
    total: float
    payment_method: str = Field("CASH", alias="paymentMethod")
    payment_status: str = Field("PENDING", alias="paymentStatus")
    settled_at: Optional[datetime] = Field(None, alias="settledAt")
    created_at: datetime = Field(..., alias="createdAt")


class SettlePaymentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    payment_method: str = Field("CASH", alias="paymentMethod")


class BillReceiptExtra(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    price: float
    total: float


class BillReceiptItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    quantity: int
    unit_price: float = Field(..., alias="unitPrice")
    total_price: float = Field(..., alias="totalPrice")
    base_unit_price: Optional[float] = Field(None, alias="baseUnitPrice")
    base_total_price: Optional[float] = Field(None, alias="baseTotalPrice")
    notes: Optional[str] = None
    extras: Optional[List[BillReceiptExtra]] = None


class IncompleteItemDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    quantity: int


class IncompleteOrderItemResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    order_id: str = Field(..., alias="orderId")
    order_number: Optional[str] = Field(None, alias="orderNumber")
    table_number: int = Field(..., alias="tableNumber")
    status: str
    items: List[IncompleteItemDetail] = Field(default_factory=list)


class BillReceiptResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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
    cgst: float = 0.0
    sgst: float = 0.0
    tax_amount: float = Field(0.0, alias="taxAmount")
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    extra_charge: float = Field(0.0, alias="extraCharge")
    amount_after_adjustments: Optional[float] = Field(0.0, alias="amountAfterAdjustments")
    round_off: float = Field(0.0, alias="roundOff")
    total: float
    payment_status: str = Field(..., alias="paymentStatus")
    created_at: str = Field(..., alias="createdAt")
    session_status: Optional[str] = Field(None, alias="sessionStatus")
    table_status: Optional[str] = Field(None, alias="tableStatus")
    has_incomplete_orders: bool = Field(False, alias="hasIncompleteOrders")
    incomplete_orders: List[IncompleteOrderItemResponse] = Field(default_factory=list, alias="incompleteOrders")
    upi_id: Optional[str] = Field("9773291261@okbizaxis", alias="upiId")
    upi_payee_name: Optional[str] = Field("OM DIYORA", alias="upiPayeeName")
    payment_qr_code: Optional[str] = Field(None, alias="paymentQrCode")


class DiningSessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    table_id: str = Field(..., alias="tableId")
    table_number: int = Field(..., alias="tableNumber")
    status: str
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    closed_at: Optional[datetime] = Field(None, alias="closedAt")
    order_count: int = Field(0, alias="orderCount")
    total_amount: float = Field(0.0, alias="totalAmount")
    payment_status: str = Field("PENDING", alias="paymentStatus")
    table_status: Optional[str] = Field(None, alias="tableStatus")


class DiningSessionDetailResponse(DiningSessionResponse):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    orders: List[Dict[str, Any]] = Field(default_factory=list)
    invoice: Optional[Dict[str, Any]] = None
    subtotal: float = 0.0
    tax: float = 0.0
    discount_percentage: float = Field(0.0, alias="discountPercentage")
    discount_amount: float = Field(0.0, alias="discountAmount")
    extra_charge: float = Field(0.0, alias="extraCharge")
    amount_after_adjustments: float = Field(0.0, alias="amountAfterAdjustments")
    round_off: float = Field(0.0, alias="roundOff")
    total: float = 0.0


class GenerateSessionBillRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    discount_percentage: Optional[float] = Field(0.0, alias="discountPercentage")
    extra_charge: Optional[float] = Field(0.0, alias="extraCharge")


class SettleSessionBillRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    payment_method: str = Field("CASH", alias="paymentMethod")
