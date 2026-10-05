import re
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token, decode_refresh_token, verify_password
from app.modules.accounts import crud
from app.modules.accounts.models import User
from app.modules.accounts.schemas import (
    UpdateProfileRequest,
    ChangePasswordRequest,
    CreateChefRequest,
    LoginRequest,
    RefreshTokenRequest,
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

        token_data = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "name": user.name,
        }
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    @staticmethod
    def refresh_token(db: Session, payload: RefreshTokenRequest) -> TokenResponse:
        try:
            token_data = decode_refresh_token(payload.refresh_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc) or "Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = token_data.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = crud.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated. Please contact administrator.",
            )

        new_data = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "name": user.name,
        }
        new_access_token = create_access_token(data=new_data)
        new_refresh_token = create_refresh_token(data=new_data)

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
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

        clean_contact = payload.contact_number.strip()
        if not re.fullmatch(r"^\d{10}$", clean_contact):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact number must be exactly 10 numeric digits.",
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

        clean_contact = payload.contact_number.strip()
        if not re.fullmatch(r"^\d{10}$", clean_contact):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact number must be exactly 10 numeric digits.",
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
    def update_profile(db: Session, current_user: User, payload: UpdateProfileRequest) -> UserResponse:
        clean_name = payload.name.strip()
        if len(clean_name) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Full Name must be at least 2 characters long.",
            )

        clean_contact = None
        if payload.contact_number is not None:
            clean_contact = payload.contact_number.strip()
            if clean_contact and not re.fullmatch(r"^\d{10}$", clean_contact):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Contact number must be exactly 10 numeric digits.",
                )

        updated = crud.update_profile(db, current_user, clean_name, clean_contact)
        return UserResponse.model_validate(updated)

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
