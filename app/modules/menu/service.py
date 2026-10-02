import re
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.menu import crud
from app.modules.menu.models import Category, MenuItem
from app.modules.menu.schemas import (
    AvailabilityUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)
from app.modules.notifications.manager import ws_manager


def _format_menu_item(item: MenuItem) -> MenuItemResponse:
    return MenuItemResponse(
        id=item.id,
        name=item.name,
        category=item.category_id,
        price=item.price,
        description=item.description,
        isVeg=item.is_veg,
        image=item.image,
        popular=item.popular,
        isAvailable=item.is_available,
        options=item.options,
        addOns=item.add_ons,
    )


class MenuService:
    # Categories
    @staticmethod
    def list_categories(db: Session, active_only: bool = True) -> List[CategoryResponse]:
        results = crud.get_categories(db, active_only=active_only)
        out = []
        for cat, count in results:
            resp = CategoryResponse.model_validate(cat)
            resp.item_count = count
            out.append(resp)
        return out

    @staticmethod
    def create_category(db: Session, payload: CategoryCreate) -> CategoryResponse:
        existing = crud.get_category_by_id(db, payload.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{payload.id}' already exists",
            )
        cat = crud.create_category(db, payload)
        return CategoryResponse.model_validate(cat)

    @staticmethod
    def update_category(db: Session, category_id: str, payload: CategoryUpdate) -> CategoryResponse:
        cat = crud.get_category_by_id(db, category_id)
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category '{category_id}' not found",
            )
        updated = crud.update_category(db, cat, payload)
        return CategoryResponse.model_validate(updated)

    @staticmethod
    def delete_category(db: Session, category_id: str) -> dict:
        cat = crud.get_category_by_id(db, category_id)
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category '{category_id}' not found",
            )
        crud.delete_category(db, cat)
        return {"message": f"Category '{category_id}' deleted successfully"}

    # Menu Items
    @staticmethod
    def list_menu_items(
        db: Session,
        category: Optional[str] = None,
        is_veg: Optional[bool] = None,
        available_only: bool = False,
    ) -> List[MenuItemResponse]:
        items = crud.get_menu_items(db, category_id=category, is_veg=is_veg, available_only=available_only)
        return [_format_menu_item(i) for i in items]

    @staticmethod
    def get_menu_item(db: Session, item_id: str) -> MenuItemResponse:
        item = crud.get_menu_item_by_id(db, item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Menu item '{item_id}' not found",
            )
        return _format_menu_item(item)

    @staticmethod
    def create_menu_item(db: Session, payload: MenuItemCreate) -> MenuItemResponse:
        cat = crud.get_category_by_id(db, payload.category)
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{payload.category}' does not exist",
            )

        item_id = payload.id
        if not item_id:
            slug = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")
            prefix = payload.category[:2].lower()
            item_id = f"{prefix}-{slug[:15]}"

        existing = crud.get_menu_item_by_id(db, item_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Menu item with ID '{item_id}' already exists",
            )

        item = crud.create_menu_item(db, payload, item_id)
        return _format_menu_item(item)

    @staticmethod
    def update_menu_item(db: Session, item_id: str, payload: MenuItemUpdate) -> MenuItemResponse:
        item = crud.get_menu_item_by_id(db, item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Menu item '{item_id}' not found",
            )
        if payload.category:
            cat = crud.get_category_by_id(db, payload.category)
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category '{payload.category}' does not exist",
                )
        updated = crud.update_menu_item(db, item, payload)
        return _format_menu_item(updated)

    @staticmethod
    async def toggle_availability(
        db: Session, item_id: str, payload: AvailabilityUpdate
    ) -> MenuItemResponse:
        item = crud.get_menu_item_by_id(db, item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Menu item '{item_id}' not found",
            )
        updated = crud.update_menu_item_availability(db, item, payload.is_available)
        await ws_manager.notify_menu_availability_changed(item_id, payload.is_available)
        return _format_menu_item(updated)

    @staticmethod
    def delete_menu_item(db: Session, item_id: str) -> dict:
        item = crud.get_menu_item_by_id(db, item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Menu item '{item_id}' not found",
            )
        crud.delete_menu_item(db, item)
        return {"message": f"Menu item '{item_id}' deleted successfully"}
