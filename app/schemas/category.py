from typing import Optional
from pydantic import BaseModel


class CategoryBase(BaseModel):
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
    name: Optional[str] = None
    icon: Optional[str] = None
    page: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    item_count: Optional[int] = 0

    class Config:
        from_attributes = True
