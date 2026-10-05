import re
from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict, EmailStr, Field


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
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CreateChefRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    contact_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    password: str

    @field_validator("contact_number")
    @classmethod
    def validate_contact(cls, v: str) -> str:
        s = v.strip()
        if not re.match(r"^\d{10}$", s):
            raise ValueError("Phone number must contain exactly 10 digits")
        return s
    role: Optional[str] = "CHEF"
    shift: Optional[str] = "Morning"
    assigned_station: Optional[str] = "Main Kitchen"


class UpdateChefRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    contact_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    role: Optional[str] = "CHEF"

    @field_validator("contact_number")
    @classmethod
    def validate_contact(cls, v: str) -> str:
        s = v.strip()
        if not re.match(r"^\d{10}$", s):
            raise ValueError("Phone number must contain exactly 10 digits")
        return s
    password: Optional[str] = None
    shift: Optional[str] = None
    assigned_station: Optional[str] = None
    is_active: Optional[bool] = None


class UpdateProfileRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    contact_number: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")

    @field_validator("contact_number")
    @classmethod
    def validate_contact(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not re.match(r"^\d{10}$", s):
                raise ValueError("Phone number must contain exactly 10 digits")
            return s
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str
