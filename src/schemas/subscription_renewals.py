from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .subscriptions import SubscriptionSchema
    from .users import UserSchema


class SubscriptionRenewalSchema(BaseSchema):
    __tablename__ = "subscription_renewals"

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False
    )
    renewed_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    renewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    previous_billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    new_billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_overdue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subscription: Mapped[SubscriptionSchema] = relationship(
        back_populates="renewals"
    )
    renewed_by: Mapped[UserSchema] = relationship()
