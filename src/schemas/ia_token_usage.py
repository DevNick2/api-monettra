from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .accounts import AccountSchema
    from .users import UserSchema


class IaOperation(PyEnum):
    CHAT = "chat"
    OFX = "ofx"
    TOOL = "tool"


class IaTokenUsageSchema(BaseSchema):
    __tablename__ = "ia_token_usage"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    operation: Mapped[IaOperation] = mapped_column(
        Enum(IaOperation, name="ia_operation", native_enum=True, create_type=False),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    account: Mapped[AccountSchema] = relationship()
    user: Mapped[UserSchema | None] = relationship()
