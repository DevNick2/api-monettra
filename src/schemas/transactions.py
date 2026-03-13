from __future__ import annotations

from datetime import date, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .users import UserSchema
    from .categories import CategorySchema


class TransactionType(PyEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionSchema(BaseSchema):
    __tablename__ = "transactions"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=True),
        nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # FKs
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )

    # Relationships
    user: Mapped["UserSchema"] = relationship(back_populates="transactions")
    category: Mapped["CategorySchema"] = relationship(back_populates="transactions")
