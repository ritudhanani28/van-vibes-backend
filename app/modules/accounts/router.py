from typing import List
from fastapi import APIRouter, status

from app.modules.accounts import apis
from app.modules.accounts.schemas import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

# Authentication
router.post("/login", response_model=TokenResponse)(apis.login)
router.post("/refresh", response_model=TokenResponse)(apis.refresh_token)
router.post("/refresh-token", response_model=TokenResponse)(apis.refresh_token)
router.get("/me", response_model=UserResponse)(apis.get_me)
router.patch("/profile", response_model=UserResponse)(apis.update_profile)
router.put("/me", response_model=UserResponse)(apis.update_profile)
router.post("/change-password")(apis.change_password)

# Chef & Staff Management (under /auth/chefs)
router.get("/chefs", response_model=List[UserResponse])(apis.list_chefs)
router.post("/chefs", response_model=UserResponse, status_code=status.HTTP_201_CREATED)(apis.create_chef)
router.put("/chefs/{chef_id}", response_model=UserResponse)(apis.update_chef)
router.delete("/chefs/{chef_id}")(apis.delete_chef)
