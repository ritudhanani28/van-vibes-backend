from typing import List
from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.accounts.schemas import (
    ChangePasswordRequest,
    CreateChefRequest,
    LoginRequest,
    TokenResponse,
    UpdateChefRequest,
    UserResponse,
)
from app.modules.accounts.service import AccountService


def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate staff / admin credentials and return JWT bearer token."""
    return AccountService.authenticate(db, payload)


def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return profile for the currently authenticated user."""
    return UserResponse.model_validate(current_user)


def list_chefs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> List[UserResponse]:
    """List all chef accounts (Admin only)."""
    return AccountService.list_chefs(db)


def create_chef(
    payload: CreateChefRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """Create a new chef / staff account (Admin only)."""
    return AccountService.create_chef(db, payload)


def update_chef(
    chef_id: str,
    payload: UpdateChefRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """Update chef account details (Admin only)."""
    return AccountService.update_chef(db, chef_id, payload)


def delete_chef(
    chef_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """Delete a chef account (Admin only)."""
    return AccountService.delete_chef(db, chef_id, admin)


def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Allow authenticated user to change their own password."""
    return AccountService.change_password(db, current_user, payload)
