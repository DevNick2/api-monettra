from __future__ import annotations
from typing import TYPE_CHECKING, List

from sqlalchemy import String, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema
from .transactions import TransactionType

DEFAULT_CATEGORIES = [
    {"title": "Moradia",      "color": "#8b6914", "icon_name": "Home", "type": TransactionType.EXPENSE},
    {"title": "Transporte",   "color": "#5a6e8b", "icon_name": "Car", "type": TransactionType.EXPENSE},
    {"title": "Lazer",        "color": "#7a5a8b", "icon_name": "Gamepad2", "type": TransactionType.EXPENSE},
    {"title": "Educação",     "color": "#5a8b6e", "icon_name": "GraduationCap", "type": TransactionType.EXPENSE},
    {"title": "Investimentos","color": "#8b7a5a", "icon_name": "Briefcase", "type": TransactionType.EXPENSE},
    {"title": "Saúde",        "color": "#a63d2f", "icon_name": "Heart", "type": TransactionType.EXPENSE},
    {"title": "Salário",      "color": "#4a7a4a", "icon_name": "DollarSign", "type": TransactionType.INCOME},
]

if TYPE_CHECKING:
    from .users import UserSchema
    from .transactions import TransactionSchema


class CategorySchema(BaseSchema):
    __tablename__ = "categories"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str] = mapped_column(String(255), nullable=False)
    icon_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=True),
        nullable=True
    )

    # FK
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Relationships
    user: Mapped["UserSchema"] = relationship(back_populates="categories")
    transactions: Mapped[List["TransactionSchema"]] = relationship(back_populates="category")
