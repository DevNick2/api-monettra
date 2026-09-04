from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.schemas.account_invites import AccountInviteSchema, InviteStatus


class AccountInviteRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def create(
        self,
        account_id: int,
        email: str,
        token_hash: str,
        expires_at: datetime,
    ) -> AccountInviteSchema:
        invite = AccountInviteSchema(
            account_id=account_id,
            email=email,
            token_hash=token_hash,
            status=InviteStatus.PENDING,
            expires_at=expires_at,
        )
        self.session.add(invite)
        self.session.commit()
        self.session.refresh(invite)
        return invite

    def find_by_token_hash(self, token_hash: str) -> AccountInviteSchema | None:
        return self.session.execute(
            select(AccountInviteSchema).where(
                AccountInviteSchema.token_hash == token_hash,
                AccountInviteSchema.deleted_at == None,  # noqa: E711
            )
        ).scalar_one_or_none()

    def find_active_by_email_and_account(
        self, account_id: int, email: str
    ) -> AccountInviteSchema | None:
        """Retorna convite pendente/sent/viewed para o e-mail nesta conta."""
        return self.session.execute(
            select(AccountInviteSchema).where(
                AccountInviteSchema.account_id == account_id,
                AccountInviteSchema.email == email,
                AccountInviteSchema.status.in_(
                    [InviteStatus.PENDING, InviteStatus.SENT, InviteStatus.VIEWED]
                ),
                AccountInviteSchema.revoked_at == None,  # noqa: E711
                AccountInviteSchema.deleted_at == None,  # noqa: E711
            )
        ).scalar_one_or_none()

    def list_by_account(self, account_id: int) -> list[AccountInviteSchema]:
        return (
            self.session.execute(
                select(AccountInviteSchema)
                .where(
                    AccountInviteSchema.account_id == account_id,
                    AccountInviteSchema.deleted_at == None,  # noqa: E711
                )
                .order_by(AccountInviteSchema.created_at.desc())
            )
            .scalars()
            .all()
        )

    def update_status(
        self, invite: AccountInviteSchema, status: InviteStatus
    ) -> AccountInviteSchema:
        invite.status = status
        invite.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(invite)
        return invite

    def revoke(self, invite: AccountInviteSchema) -> AccountInviteSchema:
        invite.revoked_at = datetime.now(timezone.utc)
        invite.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(invite)
        return invite

    def delete(self, invite: AccountInviteSchema) -> None:
        """Remove definitivamente o convite (após cadastro concluído)."""
        self.session.delete(invite)
        self.session.commit()
