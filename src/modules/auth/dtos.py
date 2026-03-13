from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class RegisterDTO(BaseModel):
    name: str
    email: EmailStr
    password: str  # mínimo 8 caracteres — validar no service


class LoginDTO(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    code: UUID
    name: str
    email: str
    type: str
    created_at: datetime

    model_config = {"from_attributes": True}
