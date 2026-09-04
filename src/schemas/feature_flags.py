from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .accounts import AccountSchema


class FeatureFlagSchema(BaseSchema):
    __tablename__ = "feature_flags"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled_global: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    overrides: Mapped[list[AccountFeatureFlagSchema]] = relationship(
        back_populates="flag", cascade="all, delete-orphan"
    )


class AccountFeatureFlagSchema(BaseSchema):
    __tablename__ = "account_feature_flags"

    __table_args__ = (
        UniqueConstraint("account_id", "flag_name", name="uq_account_feature_flag"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    flag_name: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("feature_flags.name", ondelete="CASCADE"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    account: Mapped[AccountSchema] = relationship()
    flag: Mapped[FeatureFlagSchema] = relationship(back_populates="overrides")
