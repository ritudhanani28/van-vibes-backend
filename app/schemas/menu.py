from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MenuItemCreate(BaseModel):
    id: Optional[str] = None
    name: str
    category: str
    price: float
    description: Optional[str] = None
    is_veg: bool = Field(True, alias="isVeg")
    image: Optional[str] = None
    popular: bool = False
    is_available: bool = Field(True, alias="isAvailable")
    options: Optional[List[Dict[str, Any]]] = None
    add_ons: Optional[List[Dict[str, Any]]] = Field(None, alias="addOns")

    class Config:
        populate_by_name = True


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    is_veg: Optional[bool] = Field(None, alias="isVeg")
    image: Optional[str] = None
    popular: Optional[bool] = None
    is_available: Optional[bool] = Field(None, alias="isAvailable")
    options: Optional[List[Dict[str, Any]]] = None
    add_ons: Optional[List[Dict[str, Any]]] = Field(None, alias="addOns")

    class Config:
        populate_by_name = True


class AvailabilityUpdate(BaseModel):
    is_available: bool = Field(..., alias="isAvailable")

    class Config:
        populate_by_name = True


class MenuItemResponse(BaseModel):
    id: str
    name: str
    category: str
    price: float
    description: Optional[str] = None
    is_veg: bool = Field(True, alias="isVeg")
    image: Optional[str] = None
    popular: bool = False
    is_available: bool = Field(True, alias="isAvailable")
    options: Optional[List[Dict[str, Any]]] = None
    add_ons: Optional[List[Dict[str, Any]]] = Field(None, alias="addOns")

    class Config:
        populate_by_name = True
        from_attributes = True
