from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.schemas.accounts import AccountSchema, AccountMemberSchema, AccountMemberRole


class AccountRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def create(self, data: dict) -> AccountSchema:
        account = AccountSchema(**data)
        self.session.add(account)
        self.session.commit()
        self.session.refresh(account)
        return account

    def find_by_code(self, code: UUID) -> AccountSchema | None:
        return self.session.execute(
            select(AccountSchema)
            .where(AccountSchema.code == code)
            .where(AccountSchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

    def find_by_id(self, account_id: int) -> AccountSchema | None:
        return self.session.execute(
            select(AccountSchema)
            .where(AccountSchema.id == account_id)
            .where(AccountSchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

    def find_membership(self, account_id: int, user_id: int) -> AccountMemberSchema | None:
        """Verifica se um usuário é membro de uma conta."""
        return self.session.execute(
            select(AccountMemberSchema)
            .where(AccountMemberSchema.account_id == account_id)
            .where(AccountMemberSchema.user_id == user_id)
            .where(AccountMemberSchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

    def find_account_by_user(self, user_id: int) -> AccountSchema | None:
        """Retorna a conta ativa do usuário (a que ele é membro)."""
        return self.session.execute(
            select(AccountSchema)
            .join(AccountMemberSchema, AccountMemberSchema.account_id == AccountSchema.id)
            .where(AccountMemberSchema.user_id == user_id)
            .where(AccountMemberSchema.is_accepted == True)  # noqa: E712
            .where(AccountMemberSchema.deleted_at == None)  # noqa: E711
            .where(AccountSchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

    def count_members(self, account_id: int) -> int:
        """Retorna o número de membros ativos da conta."""
        result = self.session.execute(
            select(AccountMemberSchema)
            .where(AccountMemberSchema.account_id == account_id)
            .where(AccountMemberSchema.is_accepted == True)  # noqa: E712
            .where(AccountMemberSchema.deleted_at == None)  # noqa: E711
        ).scalars().all()
        return len(result)

    def add_member(
        self,
        account_id: int,
        user_id: int,
        role: AccountMemberRole = AccountMemberRole.USER,
        is_accepted: bool = True,
    ) -> AccountMemberSchema:
        member = AccountMemberSchema(
            account_id=account_id,
            user_id=user_id,
            role=role,
            is_accepted=is_accepted,
        )
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member

    def list_members(self, account_id: int) -> list[AccountMemberSchema]:
        return self.session.execute(
            select(AccountMemberSchema)
            .where(AccountMemberSchema.account_id == account_id)
            .where(AccountMemberSchema.deleted_at == None)  # noqa: E711
        ).scalars().all()

    def remove_member(self, member: AccountMemberSchema) -> None:
        member.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
