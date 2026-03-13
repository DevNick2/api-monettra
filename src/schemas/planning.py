from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema
from .transactions import TransactionType

if TYPE_CHECKING:
    from .users import UserSchema
    from .categories import CategorySchema


class PlanningEntrySchema(BaseSchema):
    __tablename__ = "planning_entries"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=True),
        nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    installment_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    installment_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    group_code: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), default=None, nullable=True
    )

    is_materialized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    materialized_transaction_code: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), default=None, nullable=True
    )

    # FKs
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )

    # Relationships
    user: Mapped["UserSchema"] = relationship(foreign_keys=[user_id])
    category: Mapped["CategorySchema"] = relationship(foreign_keys=[category_id])
