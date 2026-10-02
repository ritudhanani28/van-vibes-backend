from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.menu.models import Category, MenuItem
from app.modules.menu.schemas import (
    CategoryCreate,
    CategoryUpdate,
    MenuItemCreate,
    MenuItemUpdate,
)


# Categories
def get_categories(db: Session, active_only: bool = True) -> List[tuple]:
    query = (
        db.query(Category, func.count(MenuItem.id).label("item_count"))
        .outerjoin(MenuItem, MenuItem.category_id == Category.id)
    )
    if active_only:
        query = query.filter(Category.is_active == True)
    return query.group_by(Category.id).order_by(Category.display_order.asc()).all()


def get_category_by_id(db: Session, category_id: str) -> Optional[Category]:
    return db.query(Category).filter(Category.id == category_id).first()


def create_category(db: Session, payload: CategoryCreate) -> Category:
    cat = Category(
        id=payload.id or payload.slug,
        name=payload.name,
        slug=payload.slug,
        icon=payload.icon,
        page=payload.page,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, category: Category, payload: CategoryUpdate) -> Category:
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, val)
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category: Category) -> None:
    db.delete(category)
    db.commit()


# Menu Items
def get_menu_items(
    db: Session,
    category_id: Optional[str] = None,
    is_veg: Optional[bool] = None,
    available_only: bool = False,
) -> List[MenuItem]:
    query = db.query(MenuItem)
    if category_id:
        query = query.filter(MenuItem.category_id == category_id)
    if is_veg is not None:
        query = query.filter(MenuItem.is_veg == is_veg)
    if available_only:
        query = query.filter(MenuItem.is_available == True)
    return query.order_by(MenuItem.name.asc()).all()


def get_menu_item_by_id(db: Session, item_id: str) -> Optional[MenuItem]:
    return db.query(MenuItem).filter(MenuItem.id == item_id).first()


def create_menu_item(db: Session, payload: MenuItemCreate, item_id: str) -> MenuItem:
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
    return item


def update_menu_item(db: Session, item: MenuItem, payload: MenuItemUpdate) -> MenuItem:
    update_data = payload.model_dump(exclude_unset=True)
    if "category" in update_data:
        update_data["category_id"] = update_data.pop("category")
    for field, val in update_data.items():
        setattr(item, field, val)
    db.commit()
    db.refresh(item)
    return item


def update_menu_item_availability(db: Session, item: MenuItem, is_available: bool) -> MenuItem:
    item.is_available = is_available
    db.commit()
    db.refresh(item)
    return item


def delete_menu_item(db: Session, item: MenuItem) -> None:
    db.delete(item)
    db.commit()
