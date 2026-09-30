from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.category import Category
from app.models.menu import MenuItem
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    """List all categories ordered by display_order with dynamic item counts."""
    # Query categories and count items per category
    item_counts = (
        db.query(MenuItem.category_id, func.count(MenuItem.id).label("cnt"))
        .group_by(MenuItem.category_id)
        .all()
    )
    counts_map = {cat_id: cnt for cat_id, cnt in item_counts}

    categories = (
        db.query(Category)
        .filter(Category.is_active == True)
        .order_by(Category.display_order.asc(), Category.name.asc())
        .all()
    )

    results = []
    for cat in categories:
        res = CategoryResponse(
            id=cat.id,
            name=cat.name,
            slug=cat.slug,
            icon=cat.icon,
            page=cat.page,
            display_order=cat.display_order,
            is_active=cat.is_active,
            item_count=counts_map.get(cat.id, 0),
        )
        results.append(res)
    return results


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a new category (Admin only)."""
    existing = db.query(Category).filter(Category.id == payload.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with ID '{payload.id}' already exists",
        )
    cat = Category(
        id=payload.id,
        name=payload.name,
        slug=payload.slug or payload.id,
        icon=payload.icon,
        page=payload.page,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryResponse(
        id=cat.id,
        name=cat.name,
        slug=cat.slug,
        icon=cat.icon,
        page=cat.page,
        display_order=cat.display_order,
        is_active=cat.is_active,
        item_count=0,
    )
