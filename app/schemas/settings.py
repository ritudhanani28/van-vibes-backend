from typing import Optional
from pydantic import BaseModel, Field


class CafeSettingsResponse(BaseModel):
    id: str = "van-vibes"
    name: str = Field("Vaan Vibes Cafe & Restro")
    hindi_name: str = Field("वन VIBES", alias="hindiName")
    tagline: str = "Cafe & Restro • Taste the Vibe"
    address: str
    phone: str
    gstin: str = "24AAAAA0000A1Z5"
    currency: str = "₹"
    tax_rate: float = Field(0.05, alias="taxRate")

    class Config:
        populate_by_name = True
        from_attributes = True


class CafeSettingsUpdate(BaseModel):
    name: Optional[str] = None
    hindi_name: Optional[str] = Field(None, alias="hindiName")
    tagline: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    tax_rate: Optional[float] = Field(None, alias="taxRate")

    class Config:
        populate_by_name = True
