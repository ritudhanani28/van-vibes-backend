from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    slug: str
    icon: Optional[str] = "🍽️"
    page: int = 2
    display_order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    icon: Optional[str] = None
    page: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    item_count: Optional[int] = 0


class MenuItemCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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


class MenuItemUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    is_available: bool = Field(..., alias="isAvailable")


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

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
