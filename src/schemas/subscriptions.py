from __future__ import annotations

from datetime import date
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .accounts import AccountSchema
    from .subscription_renewals import SubscriptionRenewalSchema
    from .transactions import TransactionSchema
    from .users import UserSchema


class RecurrenceType(PyEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionPaymentMethod(PyEnum):
    DEFAULT = "default"
    CREDIT_CARD = "credit_card"

class SubscriptionSchema(BaseSchema):
    __tablename__ = "subscriptions"

    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    # amount: Mapped[int] = mapped_column(Integer, nullable=False)
    recurrence: Mapped[RecurrenceType] = mapped_column(
        Enum(RecurrenceType, name="recurrence_type", native_enum=True),
        nullable=False,
    )
    # Data completa da assinatura/renovação (substitui billing_day)
    billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    has_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Método de pagamento — preparatório para integração com cartões
    payment_method: Mapped[SubscriptionPaymentMethod] = mapped_column(
        Enum(
            SubscriptionPaymentMethod,
            name="subscription_payment_method",
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=SubscriptionPaymentMethod.DEFAULT,
        server_default="default",
    )

    # Descrição/notas opcionais
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # FKs
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    # Relationships
    user: Mapped[UserSchema] = relationship(back_populates="subscriptions")
    account: Mapped[AccountSchema] = relationship(back_populates="subscriptions")
    transactions: Mapped[list[TransactionSchema]] = relationship(back_populates="subscription", cascade="all, delete-orphan")
    renewals: Mapped[list[SubscriptionRenewalSchema]] = relationship(back_populates="subscription", cascade="all, delete-orphan")

    @property
    def amount(self) -> int:
        return self.transactions[0].amount if self.transactions else 0

    @property
    def icon_name(self) -> str | None:
        return None
