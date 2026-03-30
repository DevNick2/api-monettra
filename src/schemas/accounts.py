from __future__ import annotations

from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List

from sqlalchemy import String, ForeignKey, Enum, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSchema

if TYPE_CHECKING:
    from .users import UserSchema
    from .transactions import TransactionSchema
    from .categories import CategorySchema
    from .subscriptions import SubscriptionSchema


class AccountMemberRole(PyEnum):
    OWNER = "owner"
    USER = "user"


class AccountSchema(BaseSchema):
    """
    Conta compartilhada do Monettra (Family/Workspace).
    Um Account abriga múltiplos UserSchema via AccountMemberSchema.
    """
    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Máximo de membros permitidos (baseado em plano)
    max_members: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    members: Mapped[List["AccountMemberSchema"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan"
    )
    transactions: Mapped[List["TransactionSchema"]] = relationship(back_populates="account")
    categories: Mapped[List["CategorySchema"]] = relationship(back_populates="account")
    subscriptions: Mapped[List["SubscriptionSchema"]] = relationship(back_populates="account")


class AccountMemberSchema(BaseSchema):
    """
    Tabela de junção Account ↔ User com role e status de convite.
    """
    __tablename__ = "account_members"

    role: Mapped[AccountMemberRole] = mapped_column(
        Enum(AccountMemberRole, name="account_member_role", native_enum=True),
        nullable=False,
        default=AccountMemberRole.USER
    )
    # True = convite aceito; False = convite pendente
    is_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # FKs
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Relationships
    account: Mapped["AccountSchema"] = relationship(back_populates="members")
    user: Mapped["UserSchema"] = relationship(back_populates="account_memberships")
