from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    contact_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    password: str
    role: Optional[str] = "CHEF"
    shift: Optional[str] = "Morning"
    assigned_station: Optional[str] = "Main Kitchen"


class UpdateChefRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    contact_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    role: Optional[str] = "CHEF"
    password: Optional[str] = None
    shift: Optional[str] = None
    assigned_station: Optional[str] = None
    is_active: Optional[bool] = None


class UpdateProfileRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    contact_number: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str
