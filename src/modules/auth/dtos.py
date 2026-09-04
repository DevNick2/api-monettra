from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


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


class GoogleCallbackDTO(BaseModel):
    """
    Payload enviado pelo frontend após autenticacão com Google.
    O frontend obteve o id_token via Google OAuth na tela de login.
    """
    id_token: str
    # Avatar e display_name opcionais (fallback caso o ID token não tenha)
    display_name: str | None = None
    avatar_url: str | None = None
