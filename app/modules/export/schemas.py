from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


ExportCategory = Literal[
    "orders",
    "order_items",
    "bills",
    "payments",
    "menu_items",
    "tables",
    "staff",
]

DateRangeType = Literal[
    "last_1_day",
    "last_7_days",
    "last_30_days",
    "custom",
    "all_time",
]


class ExportFilters(BaseModel):
    # Orders filters
    order_status: Optional[str] = Field(None, alias="orderStatus")
    order_id: Optional[str] = Field(None, alias="orderId")
    table_number: Optional[int] = Field(None, alias="tableNumber")

    # Bills & Payments filters
    bill_payment_status: Optional[str] = Field(None, alias="billPaymentStatus")
    bill_payment_method: Optional[str] = Field(None, alias="billPaymentMethod")
    bill_number: Optional[str] = Field(None, alias="billNumber")

    # Menu items filters
    menu_category: Optional[str] = Field(None, alias="menuCategory")
    menu_availability: Optional[bool] = Field(None, alias="menuAvailability")

    # Tables filters
    table_status: Optional[str] = Field(None, alias="tableStatus")

    # Staff filters
    staff_role: Optional[str] = Field(None, alias="staffRole")

    model_config = {"populate_by_name": True}


class ExportRequest(BaseModel):
    categories: List[str] = Field(..., min_length=1, description="List of categories to export")
    date_range: DateRangeType = Field("last_7_days", alias="dateRange")
    start_date: Optional[str] = Field(None, alias="startDate", description="YYYY-MM-DD for custom range")
    end_date: Optional[str] = Field(None, alias="endDate", description="YYYY-MM-DD for custom range")
    filters: Optional[ExportFilters] = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_range == "custom":
            if not self.start_date or not self.end_date:
                raise ValueError("start_date and end_date are required for custom date range")
            if self.start_date > self.end_date:
                raise ValueError("Start date cannot be after end date")
        return self


class ExportPreviewResponse(BaseModel):
    counts: Dict[str, int]
    total_records: int
    date_range_label: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
