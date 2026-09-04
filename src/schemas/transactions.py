from __future__ import annotations

from datetime import date, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Uuid as SaUuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from .base import BaseSchema

if TYPE_CHECKING:
    from .users import UserSchema
    from .categories import CategorySchema
    from .accounts import AccountSchema
    from .credit_cards import InvoiceSchema


class TransactionType(PyEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionClassification(PyEnum):
    DEFAULT = "default"
    SUBSCRIPTION = "subscription"
    CREDIT_CARD = "credit_card"


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
    type_of_transaction: Mapped[TransactionClassification] = mapped_column(
        Enum(
            TransactionClassification, 
            name="transaction_classification", 
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=TransactionClassification.DEFAULT
    )

    # UUID que agrupa todas as parcelas de uma mesma recorrência
    recurrence_id: Mapped[uuid.UUID | None] = mapped_column(SaUuid(as_uuid=True), nullable=True, index=True)

    # FKs
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    # ID do usuário que criou o registro (rastreabilidade em conta compartilhada)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # FK para a fatura do cartão de crédito (nullable — ausente em transações comuns)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    # Dono da transação ("de quem é essa despesa/receita na vida real")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships
    user: Mapped["UserSchema"] = relationship(foreign_keys=[user_id], back_populates="transactions")
    category: Mapped["CategorySchema"] = relationship(back_populates="transactions")
    subscription: Mapped["SubscriptionSchema"] = relationship(back_populates="transactions")
    account: Mapped["AccountSchema"] = relationship(back_populates="transactions")
    invoice: Mapped["InvoiceSchema"] = relationship(back_populates="transactions")
    owner: Mapped["UserSchema"] = relationship(foreign_keys=[owner_id], back_populates="owned_transactions")

    @property
    def subscription_payment_method(self) -> str | None:
        if self.subscription:
            return self.subscription.payment_method.value
        return None

    @property
    def invoice_reference_month(self) -> int | None:
        return self.invoice.reference_month if self.invoice else None

    @property
    def invoice_reference_year(self) -> int | None:
        return self.invoice.reference_year if self.invoice else None

    @property
    def credit_card_name(self) -> str | None:
        return self.invoice.credit_card.name if self.invoice and self.invoice.credit_card else None
