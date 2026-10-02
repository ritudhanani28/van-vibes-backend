from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    contact_number: Optional[str] = None
    role: str
    shift: Optional[str] = "Morning"
    assigned_station: Optional[str] = "Main Kitchen"
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreateChefRequest(BaseModel):
    name: str
    email: EmailStr
    contact_number: str
    password: str
    role: Optional[str] = "CHEF"
    shift: Optional[str] = "Morning"
    assigned_station: Optional[str] = "Main Kitchen"


class UpdateChefRequest(BaseModel):
    name: str
    email: EmailStr
    contact_number: str
    role: Optional[str] = "CHEF"
    password: Optional[str] = None
    shift: Optional[str] = None
    assigned_station: Optional[str] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str
