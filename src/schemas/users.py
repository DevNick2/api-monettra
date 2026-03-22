from __future__ import annotations
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List

from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .categories import CategorySchema
    from .transactions import TransactionSchema
    from .subscriptions import SubscriptionSchema


class UserType(PyEnum):
    USER = "user"
    ADMIN = "admin"


class UserSchema(BaseSchema):
    __tablename__ = "users"

    name: Mapped[str | None] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[UserType] = mapped_column(
        Enum(UserType, name="user_type", native_enum=True),
        nullable=False,
        default=UserType.USER
    )

    # Relationships
    categories: Mapped[List["CategorySchema"]] = relationship(back_populates="user")
    transactions: Mapped[List["TransactionSchema"]] = relationship(back_populates="user")
    subscriptions: Mapped[List["SubscriptionSchema"]] = relationship(back_populates="user")