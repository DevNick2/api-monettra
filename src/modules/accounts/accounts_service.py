"""
AccountsService — Regras de negócio do módulo de contas compartilhadas.
"""

from fastapi import HTTPException, status

from src.repository.account_repository import AccountRepository
from src.repository.user_repository import UserRepository
from src.schemas.accounts import AccountMemberRole
from src.shared.utils.logger import logger
from .dtos import CreateAccountDTO, InviteMemberDTO, AccountResponse, AccountMemberResponse


class AccountsService:
    def __init__(
        self,
        repository: AccountRepository,
        user_repository: UserRepository,
    ):
        self.repository = repository
        self.user_repository = user_repository

    def create_account(self, user_id: int, data: CreateAccountDTO) -> AccountResponse:
        """
        Cria uma nova Account e designa o usuário criador como OWNER.
        """
        # Verifica se o usuário já pertence a uma conta
        # XXX FIXME :: Revisar essa lógica, faz sentido ele validar se o usuário já pertence a uma conta pelo
        # user_id antes de criar? se a intenção é identificar se o mesmo usuário que criar duas contas
        # deveria ser por e-mail e não deve travar o restante da aplicação
        existing = self.repository.find_account_by_user(user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este usuário já pertence a uma conta compartilhada"
            )

        try:
            # XXX TODO :: O max_members deveria vir do plano do usuário
            account = self.repository.create({"name": data.name, "max_members": 5})
            self.repository.add_member(
                account_id=account.id,
                user_id=user_id,
                role=AccountMemberRole.OWNER,
                is_accepted=True,
            )
            return self._build_response(account)
        except Exception as e:
            logger.error(f"Erro ao criar conta: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar conta"
            )

    def get_my_account(self, user_id: int) -> AccountResponse:
        """Retorna a conta do usuário autenticado."""
        account = self.repository.find_account_by_user(user_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada. Crie ou aguarde um convite."
            )
        return self._build_response(account)

    def invite_member(self, user_id: int, data: InviteMemberDTO) -> dict:
        """
        Convida um usuário para a conta do owner autenticado.
        Valida o limite de membros baseado em max_members da conta.
        """
        account = self.repository.find_account_by_user(user_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Você não possui uma conta para convidar membros"
            )

        # Apenas o OWNER pode convidar
        membership = self.repository.find_membership(account.id, user_id)
        if not membership or membership.role != AccountMemberRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas o dono da conta pode convidar membros"
            )

        # Verificar limite de membros
        current_count = self.repository.count_members(account.id)
        if current_count >= account.max_members:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Limite de {account.max_members} membros atingido para este plano"
            )

        # Verificar se usuário convidado existe
        invited_user = self.user_repository.find_by_email(data.email)
        if not invited_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário com este e-mail não encontrado"
            )

        # Verificar se já é membro
        existing_membership = self.repository.find_membership(account.id, invited_user.id)
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este usuário já é membro da conta"
            )
        # XXX FIXME :: Nessa etapa ele não cria um usuário
        # Ele apenas esta adicionando o usuário já existente
        # A uma conta, só que isso nunca aconteceria visto
        # Que toda a tentativa de criar usuário através do /register
        # Ou via OAuth valida se o usuário já tem conta e não deixa criar
        # A ideia aqui é o seguinte: Nessa etapa deve enviar um e-mail
        # Para o usuário convidado com um link, e a partir disso ele cria seu usuário
        # Usando o account_code para vincular a conta
        try:
            self.repository.add_member(
                account_id=account.id,
                user_id=invited_user.id,
                role=AccountMemberRole.USER,
                is_accepted=True,  # Simplificado: aceito automaticamente
            )
            return {"message": f"Usuário {invited_user.name or invited_user.email} adicionado com sucesso"}
        except Exception as e:
            logger.error(f"Erro ao convidar membro: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao adicionar membro"
            )

    def remove_member(self, owner_user_id: int, member_user_code: str) -> dict:
        """Remove um membro da conta. Apenas o OWNER pode remover."""
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

    # XXX TODO :: Todo o build de resposta fica no controller,
    # para uso interno deve ser o Schema.
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
