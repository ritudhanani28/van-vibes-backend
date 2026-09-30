from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CreateChefRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate Admin or Chef and return signed JWT access token."""
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact your manager.",
        )

    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "name": user.name,
    }
    access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get authenticated user profile."""
    return UserResponse.model_validate(current_user)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """Logout current user."""
    return {"message": "Logged out successfully", "user_id": current_user.id}


@router.get("/chefs", response_model=List[UserResponse])
def list_chefs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all chef accounts (Admin only). Passwords are never returned."""
    chefs = db.query(User).filter(User.role == "CHEF").order_by(User.created_at.desc()).all()
    return [UserResponse.model_validate(c) for c in chefs]


@router.post("/chefs", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_chef(
    payload: CreateChefRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Create a new chef account (Admin only).
    The CHEF role is strictly assigned by the backend. Passwords are never returned.
    """
    clean_email = payload.email.lower().strip()
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{clean_email}' already exists.",
        )

    if len(payload.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long.",
        )

    chef = User(
        email=clean_email,
        name=payload.name.strip(),
        contact_number=payload.contact_number.strip(),
        password_hash=hash_password(payload.password),
        role="CHEF",  # Strictly assigned by backend
        assigned_station="Main Kitchen",
        shift="Active Duty",
        is_active=True,
    )
    db.add(chef)
    db.commit()
    db.refresh(chef)

    return UserResponse.model_validate(chef)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Allow authenticated user (e.g. Chef) to change their own password.
    Validates current password, password requirements, and confirmation match.
    """
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

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()

    return {"message": "Password changed successfully."}
