from __future__ import annotations

from datetime import date
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, String, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from .base import BaseSchema

if TYPE_CHECKING:
    from .users import UserSchema
    from .accounts import AccountSchema


class RecurrenceType(PyEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    BIANNUAL = "biannual"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"


class SubscriptionPaymentMethod(PyEnum):
    DEFAULT = "default"
    CREDIT_CARD = "credit_card"

# Vou fazer alguns ajustes:
# 1) Remover o Amount;
# 2) remover o icon_name;
# 3) Adicionar a relação com transactions;
# 4) Adicionar uma coluna chamada type_of_transaction no schema transactions;
# 5) Revisar o subscription_service para que quando criar uma assinatura, adicione a relação nos lançamentos;
# 6) Transações com type_of_transction=subscription não tem a opção de editar ou remover;
# 7) Ajustar para que na listagem de transações apareça as assinaturas, porém apenas as assinaturas que estão ativas;

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
    user: Mapped["UserSchema"] = relationship(back_populates="subscriptions")
    account: Mapped["AccountSchema"] = relationship(back_populates="subscriptions")
    transactions: Mapped[list["TransactionSchema"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")

    @property
    def amount(self) -> int:
        return self.transactions[0].amount if self.transactions else 0

    @property
    def icon_name(self) -> str | None:
        return None
