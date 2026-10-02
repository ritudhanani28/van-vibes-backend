from typing import List, Optional
from fastapi import Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin, require_chef_or_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.menu.schemas import (
    AvailabilityUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)
from app.modules.menu.service import MenuService


# Categories
def list_categories(
    active_only: bool = True,
    db: Session = Depends(get_db),
) -> List[CategoryResponse]:
    """List all categories with live item count."""
    return MenuService.list_categories(db, active_only=active_only)


def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> CategoryResponse:
    """Create a new category (Admin only)."""
    return MenuService.create_category(db, payload)


def update_category(
    category_id: str,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> CategoryResponse:
    """Update category metadata (Admin only)."""
    return MenuService.update_category(db, category_id, payload)


def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """Delete category and cascade items (Admin only)."""
    return MenuService.delete_category(db, category_id)


# Menu Items
def list_menu_items(
    category: Optional[str] = Query(None),
    is_veg: Optional[bool] = Query(None),
    available_only: bool = Query(False),
    db: Session = Depends(get_db),
) -> List[MenuItemResponse]:
    """List all menu items with category / veg filter."""
    return MenuService.list_menu_items(db, category=category, is_veg=is_veg, available_only=available_only)


def get_menu_item(
    item_id: str,
    db: Session = Depends(get_db),
) -> MenuItemResponse:
    """Get single menu item details."""
    return MenuService.get_menu_item(db, item_id)


def create_menu_item(
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> MenuItemResponse:
    """Create a new menu item (Admin only)."""
    return MenuService.create_menu_item(db, payload)


def update_menu_item(
    item_id: str,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> MenuItemResponse:
    """Update menu item details (Admin only)."""
    return MenuService.update_menu_item(db, item_id, payload)


async def toggle_availability(
    item_id: str,
    payload: AvailabilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_chef_or_admin),
) -> MenuItemResponse:
    """Toggle 86 / availability for an item (Chef or Admin). Broadcasts live availability update."""
    return await MenuService.toggle_availability(db, item_id, payload)


def delete_menu_item(
    item_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """Delete a menu item (Admin only)."""
    return MenuService.delete_menu_item(db, item_id)
