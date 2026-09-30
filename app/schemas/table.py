from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.dining_session import DiningSessionResponse


class CreateTableRequest(BaseModel):
    table_number: int = Field(..., alias="tableNumber")
    capacity: Optional[int] = 4

    class Config:
        populate_by_name = True


class TableBase(BaseModel):
    id: str
    table_number: int = Field(..., alias="tableNumber")
    name: str
    token: str
    capacity: int = 4
    status: str = "AVAILABLE"  # AVAILABLE, OCCUPIED, RESERVED
    is_active: bool = True

    class Config:
        populate_by_name = True
        from_attributes = True


class TableResponse(TableBase):
    qr_code_url: Optional[str] = Field(None, alias="qrCodeUrl")
    active_session: Optional[DiningSessionResponse] = Field(None, alias="activeSession")


class TableStatusUpdate(BaseModel):
    status: str  # AVAILABLE, OCCUPIED, RESERVED


class ValidateQRRequest(BaseModel):
    table_id: str = Field(..., alias="tableId")
    token: str

    class Config:
        populate_by_name = True


class ValidateQRResponse(BaseModel):
    valid: bool
    table: Optional[TableResponse] = None
    dining_session: Optional[DiningSessionResponse] = Field(None, alias="diningSession")
    is_new_session: bool = Field(False, alias="isNewSession")
    message: Optional[str] = None

    class Config:
        populate_by_name = True


class StandeeResponse(BaseModel):
    table_id: str
    table_number: int
    name: str
    capacity: int
    scan_url: str
    qr_image_url: str
