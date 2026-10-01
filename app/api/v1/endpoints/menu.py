import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.category import Category
from app.models.menu import MenuItem
from app.models.user import User
from app.schemas.menu import AvailabilityUpdate, MenuItemCreate, MenuItemResponse, MenuItemUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/menu", tags=["Menu"])


@router.get("", response_model=List[MenuItemResponse])
def get_menu(
    category: Optional[str] = Query(None, description="Category ID or slug filter"),
    search: Optional[str] = Query(None, description="Search term for dish name"),
    is_veg: Optional[bool] = Query(None, description="Filter by vegetarian"),
    db: Session = Depends(get_db),
):
    """Retrieve full menu items with optional category filtering and food name search."""
    query = db.query(MenuItem)

    if category and category.lower() != "all":
        query = query.filter(MenuItem.category_id == category)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(MenuItem.name.ilike(search_term))

    if is_veg is not None:
        query = query.filter(MenuItem.is_veg == is_veg)

    items = query.order_by(MenuItem.name.asc()).all()
    return items


@router.get("/{item_id}", response_model=MenuItemResponse)
def get_menu_item(item_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single menu item."""
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item '{item_id}' not found",
        )
    return item


@router.post("", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
async def create_menu_item(
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Add a new dish to the menu catalog (Admin only)."""
    # Verify category exists
    cat = db.query(Category).filter(Category.id == payload.category).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category '{payload.category}' does not exist",
        )

    item_id = payload.id or f"dish-{uuid.uuid4().hex[:8]}"
    existing = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dish with ID '{item_id}' already exists",
        )

    item = MenuItem(
        id=item_id,
        category_id=payload.category,
        name=payload.name,
        price=payload.price,
        description=payload.description,
        is_veg=payload.is_veg,
        image=payload.image,
        popular=payload.popular,
        is_available=payload.is_available,
        options=payload.options,
        add_ons=payload.add_ons,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    # Broadcast real-time menu change
    await ws_manager.notify_menu_updated(MenuItemResponse.model_validate(item).model_dump(by_alias=True))
    return item


@router.put("/{item_id}", response_model=MenuItemResponse)
async def update_menu_item(
    item_id: str,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update dish details, price, or description (Admin only)."""
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item '{item_id}' not found",
        )

    if payload.category is not None:
        cat = db.query(Category).filter(Category.id == payload.category).first()
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{payload.category}' does not exist",
            )
        item.category_id = payload.category

    if payload.name is not None:
        item.name = payload.name
    if payload.price is not None:
        item.price = payload.price
    if payload.description is not None:
        item.description = payload.description
    if payload.is_veg is not None:
        item.is_veg = payload.is_veg
    if payload.image is not None:
        item.image = payload.image
    if payload.popular is not None:
        item.popular = payload.popular
    if payload.is_available is not None:
        item.is_available = payload.is_available
    if payload.options is not None:
        item.options = payload.options
    if payload.add_ons is not None:
        item.add_ons = payload.add_ons

    db.commit()
    db.refresh(item)
    # Broadcast real-time menu change
    await ws_manager.notify_menu_updated(MenuItemResponse.model_validate(item).model_dump(by_alias=True))
    return item


@router.patch("/{item_id}/availability", response_model=MenuItemResponse)
async def toggle_availability(
    item_id: str,
    payload: AvailabilityUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Instantly toggle availability of a dish (Admin only). Broadcasts WebSocket event."""
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item '{item_id}' not found",
        )

    item.is_available = payload.is_available
    db.commit()
    db.refresh(item)

    # Broadcast real-time change to all clients
    await ws_manager.notify_menu_availability_changed(item_id, item.is_available)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_200_OK)
async def delete_menu_item(
    item_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete a dish from the menu catalog (Admin only)."""
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item '{item_id}' not found",
        )
    db.delete(item)
    db.commit()
    # Broadcast real-time deletion to all connected clients
    await ws_manager.notify_menu_item_deleted(item_id)
    return {"message": f"Menu item '{item_id}' deleted successfully", "id": item_id}
