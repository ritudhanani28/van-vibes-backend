import re
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
    UpdateChefRequest,
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


def validate_password_strength(password: str) -> None:
    """Validate password has min 6 chars, uppercase, lowercase, number, and special character."""
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


@router.get("/chefs", response_model=List[UserResponse])
def list_chefs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all chef accounts (Admin only). Strictly filters role == 'CHEF'."""
    chefs = (
        db.query(User)
        .filter(User.role == "CHEF")
        .order_by(User.created_at.desc())
        .all()
    )
    return [UserResponse.model_validate(c) for c in chefs]


@router.post("/chefs", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_chef(
    payload: CreateChefRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Create a new chef / staff account (Admin only).
    Validates required email, 10-digit contact number, role, and strong password (uppercase, lowercase, number, special char).
    """
    clean_email = payload.email.lower().strip()
    existing = db.query(User).filter(User.email == clean_email).first()
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

    clean_role = payload.role.upper().strip() if payload.role else "CHEF"
    if clean_role not in ["CHEF", "ADMIN"]:
        clean_role = "CHEF"

    chef = User(
        email=clean_email,
        name=payload.name.strip(),
        contact_number=payload.contact_number.strip(),
        password_hash=hash_password(payload.password),
        role=clean_role,
        assigned_station=payload.assigned_station.strip() if payload.assigned_station else "Main Kitchen",
        shift=payload.shift.strip() if payload.shift else "Morning",
        is_active=True,
    )
    db.add(chef)
    db.commit()
    db.refresh(chef)

    return UserResponse.model_validate(chef)


@router.put("/chefs/{chef_id}", response_model=UserResponse)
def update_chef(
    chef_id: str,
    payload: UpdateChefRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Update chef account details (Admin only).
    Supports updating name, email, contact number, role, active status, and optional password.
    """
    chef = db.query(User).filter(User.id == chef_id).first()
    if not chef:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chef with id '{chef_id}' not found.",
        )

    clean_email = payload.email.lower().strip()
    if clean_email != chef.email:
        existing = db.query(User).filter(User.email == clean_email, User.id != chef_id).first()
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

    clean_role = payload.role.upper().strip() if payload.role else "CHEF"
    if clean_role not in ["CHEF", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be either CHEF or ADMIN.",
        )

    if payload.password and payload.password.strip():
        validate_password_strength(payload.password.strip())
        chef.password_hash = hash_password(payload.password.strip())

    chef.name = payload.name.strip()
    chef.email = clean_email
    chef.contact_number = payload.contact_number.strip()
    chef.role = clean_role
    if payload.shift is not None:
        chef.shift = payload.shift.strip()
    if payload.assigned_station is not None:
        chef.assigned_station = payload.assigned_station.strip()
    if payload.is_active is not None:
        chef.is_active = payload.is_active

    db.commit()
    db.refresh(chef)
    return UserResponse.model_validate(chef)


@router.delete("/chefs/{chef_id}")
def delete_chef(
    chef_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Delete a chef account (Admin only).
    Prevents deleting the active logged-in admin or default admin account.
    """
    if admin.id == chef_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own logged-in admin account.",
        )

    chef = db.query(User).filter(User.id == chef_id).first()
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
    db.delete(chef)
    db.commit()

    return {"message": f"Chef {chef_name} deleted successfully", "id": chef_id}


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
