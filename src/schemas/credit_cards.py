from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .users import UserSchema
    from .accounts import AccountSchema
    from .transactions import TransactionSchema


class CreditCardSchema(BaseSchema):
    __tablename__ = "credit_cards"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Limite em centavos
    credit_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    # Dia do mês em que a fatura fecha (1–31)
    closing_day: Mapped[int] = mapped_column(Integer, nullable=False)
    # Dia do mês em que a fatura vence (1–31)
    due_day: Mapped[int] = mapped_column(Integer, nullable=False)

    # FKs
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    # Relationships
    user: Mapped["UserSchema"] = relationship(foreign_keys=[user_id])
    account: Mapped["AccountSchema"] = relationship()
    invoices: Mapped[list["InvoiceSchema"]] = relationship(
        back_populates="credit_card",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InvoiceSchema(BaseSchema):
    __tablename__ = "invoices"

    # Mês/Ano de referência da fatura
    reference_month: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_year: Mapped[int] = mapped_column(Integer, nullable=False)
    # Somatório em centavos (atualizado a cada nova transação)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # FK
    credit_card_id: Mapped[int] = mapped_column(ForeignKey("credit_cards.id"), nullable=False)

    # Relationships
    credit_card: Mapped["CreditCardSchema"] = relationship(back_populates="invoices")
    transactions: Mapped[list["TransactionSchema"]] = relationship(
        back_populates="invoice",
        lazy="selectin",
    )
