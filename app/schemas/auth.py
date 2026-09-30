from typing import Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    contact_number: Optional[str] = None
    role: str
    shift: Optional[str] = "Morning"
    assigned_station: Optional[str] = "Main Kitchen"
    is_active: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreateChefRequest(BaseModel):
    name: str
    email: EmailStr
    contact_number: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str
