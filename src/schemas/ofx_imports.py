"""
OFX Import — Schema de rastreamento de importações OFX em background.

Status: pending → processing → completed | error
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .users import UserSchema
    from .accounts import AccountSchema


class OfxImportSchema(BaseSchema):
    __tablename__ = "ofx_imports"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="settings",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    total_transactions: Mapped[int] = mapped_column(
        Integer, nullable=True, default=0
    )
    processed_transactions: Mapped[int] = mapped_column(
        Integer, nullable=True, default=0
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # FKs
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )

    # Relationships
    user: Mapped["UserSchema"] = relationship()
    account: Mapped["AccountSchema"] = relationship()
