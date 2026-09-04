"""
AccountsService — Regras de negócio do módulo de contas compartilhadas.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from src.repository.account_invite_repository import AccountInviteRepository
from src.repository.account_repository import AccountRepository
from src.repository.user_repository import UserRepository
from src.schemas.account_invites import InviteStatus
from src.schemas.accounts import AccountMemberRole
from src.shared.services.email_service import EmailService
from src.shared.utils.auth import hash_password
from src.shared.utils.environment import environment
from src.shared.utils.logger import logger
from .dtos import (
    AccountMemberResponse,
    AccountResponse,
    CreateAccountDTO,
    InviteMemberDTO,
    InviteResponse,
    RegisterViaInviteDTO,
)

_INVITE_TTL_HOURS = 24
_APP_PUBLIC_URL = environment.get("APP_PUBLIC_URL", "http://localhost:8080")


class AccountsService:
    def __init__(
        self,
        repository: AccountRepository,
        user_repository: UserRepository,
        invite_repository: AccountInviteRepository,
        email_service: EmailService,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.invite_repository = invite_repository
        self.email_service = email_service

    # ─────────────────────────────────────────────
    # Conta
    # ─────────────────────────────────────────────

    def create_account(self, user_id: int, data: CreateAccountDTO) -> AccountResponse:
        existing = self.repository.find_account_by_user(user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este usuário já pertence a uma conta compartilhada",
            )
        try:
            account = self.repository.create({"name": data.name, "max_members": 5})
            self.repository.add_member(
                account_id=account.id,
                user_id=user_id,
                role=AccountMemberRole.OWNER,
                is_accepted=True,
            )
            return self._build_response(account)
        except Exception as exc:
            logger.error(f"Erro ao criar conta: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar conta",
            )

    def get_my_account(self, user_id: int) -> AccountResponse:
        account = self.repository.find_account_by_user(user_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada. Crie ou aguarde um convite.",
            )
        return self._build_response(account)

    def remove_member(self, owner_user_id: int, member_user_code: str) -> dict:
        account = self.repository.find_account_by_user(owner_user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Conta não encontrada")

        owner_membership = self.repository.find_membership(account.id, owner_user_id)
        if not owner_membership or owner_membership.role != AccountMemberRole.OWNER:
            raise HTTPException(status_code=403, detail="Apenas o dono pode remover membros")

        member_user = self.user_repository.find_by_code(member_user_code)
        if not member_user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        membership = self.repository.find_membership(account.id, member_user.id)
        if not membership:
            raise HTTPException(status_code=404, detail="Usuário não é membro desta conta")

        if membership.role == AccountMemberRole.OWNER:
            raise HTTPException(status_code=422, detail="Não é possível remover o dono da conta")

        self.repository.remove_member(membership)
        return {"message": "Membro removido com sucesso"}

    # ─────────────────────────────────────────────
    # Convites (autenticados — OWNER)
    # ─────────────────────────────────────────────

    def send_invite(self, user_id: int, payload: InviteMemberDTO) -> InviteResponse:
        """Cria um convite por token e envia e-mail. Rejeita e-mail já cadastrado."""
        account = self._require_owner_account(user_id)

        # Bloquear e-mail já cadastrado no sistema
        if self.user_repository.find_by_email(payload.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este e-mail já possui uma conta no Monettra. "
                       "Usuários cadastrados não podem receber convites.",
            )

        # Verificar limite de membros (membros ativos + convites ativos)
        current_members = self.repository.count_members(account.id)
        active_invites = self.invite_repository.list_by_account(account.id)
        pending_count = sum(
            1 for i in active_invites
            if i.status in (InviteStatus.PENDING, InviteStatus.SENT, InviteStatus.VIEWED)
            and i.revoked_at is None
            and i.expires_at > datetime.now(timezone.utc)
        )
        if current_members + pending_count >= account.max_members:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Limite de {account.max_members} membros atingido para este plano",
            )

        # Revogar convite anterior ativo para o mesmo e-mail (se existir)
        existing = self.invite_repository.find_active_by_email_and_account(
            account.id, payload.email
        )
        if existing:
            self.invite_repository.revoke(existing)

        # Gerar token opaco e armazenar apenas o hash
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=_INVITE_TTL_HOURS)

        invite = self.invite_repository.create(
            account_id=account.id,
            email=payload.email,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        # Enviar e-mail (falha silenciosa — status permanece PENDING se não enviar)
        invite_link = f"{_APP_PUBLIC_URL}/invite/{raw_token}"
        sent = self.email_service.send_invite(payload.email, invite_link, account.name)
        if sent:
            self.invite_repository.update_status(invite, InviteStatus.SENT)

        return self._build_invite_response(invite)

    def list_invites(self, user_id: int) -> list[InviteResponse]:
        account = self._require_owner_account(user_id)
        invites = self.invite_repository.list_by_account(account.id)
        return [self._build_invite_response(i) for i in invites]

    def resend_invite(self, user_id: int, invite_code: str) -> InviteResponse:
        account = self._require_owner_account(user_id)
        invite = self._find_invite_in_account(account.id, invite_code)

        if invite.revoked_at:
            raise HTTPException(status_code=422, detail="Convite já foi revogado")
        if invite.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=422,
                detail="Convite expirado. Crie um novo convite para este e-mail.",
            )

        # Gera novo token (invalida o anterior)
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invite.token_hash = token_hash
        invite.expires_at = datetime.now(timezone.utc) + timedelta(hours=_INVITE_TTL_HOURS)
        invite.updated_at = datetime.now(timezone.utc)
        self.invite_repository.update_status(invite, InviteStatus.PENDING)

        invite_link = f"{_APP_PUBLIC_URL}/invite/{raw_token}"
        sent = self.email_service.send_invite(invite.email, invite_link, account.name)
        if sent:
            self.invite_repository.update_status(invite, InviteStatus.SENT)

        return self._build_invite_response(invite)

    def revoke_invite(self, user_id: int, invite_code: str) -> dict:
        account = self._require_owner_account(user_id)
        invite = self._find_invite_in_account(account.id, invite_code)

        if invite.revoked_at:
            raise HTTPException(status_code=422, detail="Convite já está revogado")

        self.invite_repository.revoke(invite)
        return {"message": "Convite revogado com sucesso"}

    # ─────────────────────────────────────────────
    # Convites (públicos — sem autenticação)
    # ─────────────────────────────────────────────

    def validate_invite_token(self, raw_token: str) -> InviteResponse:
        """Valida o token e, se válido, transita para 'viewed'. Idempotente."""
        invite = self._resolve_token(raw_token)

        if invite.status == InviteStatus.VIEWED:
            return self._build_invite_response(invite)

        self.invite_repository.update_status(invite, InviteStatus.VIEWED)
        return self._build_invite_response(invite)

    def register_via_invite(
        self, raw_token: str, payload: RegisterViaInviteDTO
    ) -> dict:
        """Cria o usuário, vincula à conta e remove o convite."""
        invite = self._resolve_token(raw_token)

        if len(payload.password) < 8:
            raise HTTPException(
                status_code=422,
                detail="A senha deve ter no mínimo 8 caracteres",
            )

        # Garantia extra: e-mail ainda não cadastrado
        if self.user_repository.find_by_email(invite.email):
            raise HTTPException(
                status_code=409,
                detail="Já existe uma conta com este e-mail",
            )

        # Verificar limite antes de criar
        current_members = self.repository.count_members(invite.account_id)
        account = self.repository.find_by_id(invite.account_id)
        if current_members >= account.max_members:
            raise HTTPException(
                status_code=422,
                detail=f"Limite de {account.max_members} membros atingido para este plano",
            )

        try:
            user = self.user_repository.create({
                "name": payload.name,
                "email": invite.email,
                "password": hash_password(payload.password),
            })
            self.repository.add_member(
                account_id=invite.account_id,
                user_id=user.id,
                role=AccountMemberRole.USER,
                is_accepted=True,
            )
            # Remove convite após conclusão bem-sucedida
            self.invite_repository.delete(invite)

            from src.shared.utils.auth import create_access_token
            token = create_access_token({
                "sub": str(user.code),
                "uid": user.id,
                "type": user.type.value,
            })
            return {"access_token": token, "token_type": "bearer"}
        except Exception as exc:
            logger.error(f"Erro ao registrar via convite: {exc}")
            raise HTTPException(
                status_code=500,
                detail="Erro interno ao concluir cadastro",
            )

    # ─────────────────────────────────────────────
    # Helpers privados
    # ─────────────────────────────────────────────

    def _require_owner_account(self, user_id: int):
        account = self.repository.find_account_by_user(user_id)
        if not account:
            raise HTTPException(status_code=404, detail="Conta não encontrada")
        membership = self.repository.find_membership(account.id, user_id)
        if not membership or membership.role != AccountMemberRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Apenas o dono da conta pode gerenciar convites"
            )
        return account

    def _find_invite_in_account(self, account_id: int, invite_code: str):
        from uuid import UUID
        try:
            code_uuid = UUID(invite_code)
        except ValueError:
            raise HTTPException(status_code=404, detail="Convite não encontrado")

        invites = self.invite_repository.list_by_account(account_id)
        invite = next((i for i in invites if i.code == code_uuid), None)
        if not invite:
            raise HTTPException(status_code=404, detail="Convite não encontrado")
        return invite

    def _resolve_token(self, raw_token: str):
        """Resolve raw token → invite; valida expiração e revogação."""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invite = self.invite_repository.find_by_token_hash(token_hash)
        if not invite:
            raise HTTPException(status_code=404, detail="Link de convite inválido")
        if invite.revoked_at:
            raise HTTPException(status_code=410, detail="Este convite foi revogado")
        if invite.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Este convite expirou")
        return invite

    def _build_response(self, account) -> AccountResponse:
        members_raw = self.repository.list_members(account.id)
        members = [
            AccountMemberResponse(
                code=m.code,
                user_code=m.user.code,
                user_name=m.user.name or "",
                user_email=m.user.email,
                role=m.role.value,
                is_accepted=m.is_accepted,
                created_at=m.created_at,
            )
            for m in members_raw
        ]
        return AccountResponse(
            code=account.code,
            name=account.name,
            max_members=account.max_members,
            is_active=account.is_active,
            created_at=account.created_at,
            members=members,
        )

    def _build_invite_response(self, invite) -> InviteResponse:
        return InviteResponse(
            code=invite.code,
            email=invite.email,
            status=invite.status.value,
            expires_at=invite.expires_at,
            revoked_at=invite.revoked_at,
            created_at=invite.created_at,
        )
