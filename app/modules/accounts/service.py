import re
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.modules.accounts import crud
from app.modules.accounts.models import User
from app.modules.accounts.schemas import (
    ChangePasswordRequest,
    CreateChefRequest,
    LoginRequest,
    TokenResponse,
    UpdateChefRequest,
    UserResponse,
)


def validate_password_strength(password: str) -> None:
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long.",
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter (A-Z).",
        )
    if not re.search(r"[a-z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one lowercase letter (a-z).",
        )
    if not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number (0-9).",
        )
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one special character (!@#$%^&*...).",
        )


class AccountService:
    @staticmethod
    def authenticate(db: Session, payload: LoginRequest) -> TokenResponse:
        user = crud.get_user_by_email(db, payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated. Please contact administrator.",
            )

        token = create_access_token(
            data={
                "sub": user.id,
                "email": user.email,
                "role": user.role,
                "name": user.name,
            }
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    @staticmethod
    def list_chefs(db: Session) -> List[UserResponse]:
        chefs = crud.get_chefs(db)
        return [UserResponse.model_validate(c) for c in chefs]

    @staticmethod
    def create_chef(db: Session, payload: CreateChefRequest) -> UserResponse:
        clean_email = payload.email.lower().strip()
        existing = crud.get_user_by_email(db, clean_email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email '{clean_email}' already exists.",
            )

        clean_digits = re.sub(r"\D", "", payload.contact_number)
        if len(clean_digits) < 10 or len(clean_digits) > 15:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact number must contain at least 10 digits.",
            )

        validate_password_strength(payload.password)
        chef = crud.create_chef(db, payload)
        return UserResponse.model_validate(chef)

    @staticmethod
    def update_chef(db: Session, chef_id: str, payload: UpdateChefRequest) -> UserResponse:
        chef = crud.get_user_by_id(db, chef_id)
        if not chef:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chef with id '{chef_id}' not found.",
            )

        clean_email = payload.email.lower().strip()
        if clean_email != chef.email:
            existing = crud.get_user_by_email(db, clean_email)
            if existing and existing.id != chef_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with email '{clean_email}' already exists.",
                )

        clean_digits = re.sub(r"\D", "", payload.contact_number)
        if len(clean_digits) < 10 or len(clean_digits) > 15:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact number must contain at least 10 digits.",
            )

        clean_role = payload.role.upper().strip() if payload.role else "CHEF"
        if clean_role not in ["CHEF", "ADMIN"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role must be either CHEF or ADMIN.",
            )

        if payload.password and payload.password.strip():
            validate_password_strength(payload.password.strip())

        updated = crud.update_chef(db, chef, payload)
        return UserResponse.model_validate(updated)

    @staticmethod
    def delete_chef(db: Session, chef_id: str, admin: User) -> dict:
        if admin.id == chef_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot delete your own logged-in admin account.",
            )

        chef = crud.get_user_by_id(db, chef_id)
        if not chef:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chef with id '{chef_id}' not found.",
            )

        if chef.email == "admin@vaanvibes.com":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Default administrator account cannot be deleted.",
            )

        chef_name = chef.name
        crud.delete_chef(db, chef)
        return {"message": f"Chef {chef_name} deleted successfully", "id": chef_id}

    @staticmethod
    def change_password(db: Session, current_user: User, payload: ChangePasswordRequest) -> dict:
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )

        if payload.new_password != payload.confirm_new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password and confirm password do not match.",
            )

        if len(payload.new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 6 characters long.",
            )

        if verify_password(payload.new_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be the same as current password.",
            )

        crud.update_password(db, current_user, payload.new_password)
        return {"message": "Password changed successfully."}
