from datetime import datetime
from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional


class CreateAccountDTO(BaseModel):
    name: str


class InviteMemberDTO(BaseModel):
    email: EmailStr


class AccountMemberResponse(BaseModel):
    code: UUID
    user_code: UUID
    user_name: str
    user_email: str
    role: str
    is_accepted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountResponse(BaseModel):
    code: UUID
    name: str
    max_members: int
    is_active: bool
    created_at: datetime
    members: list[AccountMemberResponse] = []

    model_config = {"from_attributes": True}


class InviteResponse(BaseModel):
    code: UUID
    email: str
    status: str
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterViaInviteDTO(BaseModel):
    name: str
    password: str
