from typing import List
from fastapi import APIRouter, status

from app.modules.menu import apis
from app.modules.menu.schemas import CategoryResponse, MenuItemResponse

# Category Router (prefix: /categories)
categories_router = APIRouter(prefix="/categories", tags=["Categories"])
categories_router.get("", response_model=List[CategoryResponse])(apis.list_categories)
categories_router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)(apis.create_category)
categories_router.put("/{category_id}", response_model=CategoryResponse)(apis.update_category)
categories_router.delete("/{category_id}")(apis.delete_category)

# Menu Router (prefix: /menu)
menu_router = APIRouter(prefix="/menu", tags=["Menu"])
menu_router.get("", response_model=List[MenuItemResponse])(apis.list_menu_items)
menu_router.get("/{item_id}", response_model=MenuItemResponse)(apis.get_menu_item)
menu_router.post("", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)(apis.create_menu_item)
menu_router.put("/{item_id}", response_model=MenuItemResponse)(apis.update_menu_item)
menu_router.patch("/{item_id}/availability", response_model=MenuItemResponse)(apis.toggle_availability)
menu_router.delete("/{item_id}")(apis.delete_menu_item)

# Combined Router
router = APIRouter()
router.include_router(categories_router)
router.include_router(menu_router)
