from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime


class UpdateUserDTO(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class UserResponse(BaseModel):
    code: UUID4
    name: Optional[str]
    email: str
    type: str
    created_at: datetime

    model_config = {"from_attributes": True}
