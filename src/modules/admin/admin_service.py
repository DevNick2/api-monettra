"""
AdminService — Regras de negócio do painel administrativo.
"""

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status

from src.repository.account_repository import AccountRepository
from src.repository.feature_flag_repository import FeatureFlagRepository
from src.repository.ia_token_usage_repository import IaTokenUsageRepository
from src.repository.user_repository import UserRepository
from src.schemas.users import UserType
from src.shared.utils.auth import hash_password
from src.shared.utils.logger import logger

from .dtos import (
    AccountFeatureFlagResponse,
    AccountMemberSummary,
    AccountSummary,
    CreateUserAdminDTO,
    FeatureFlagAdminResponse,
    PaginatedTokenUsageResponse,
    PaginatedUsersResponse,
    TokenUsageAggregatedResponse,
    TokenUsageDetailResponse,
    UpdateFeatureFlagDTO,
    UpdateUserAdminDTO,
    UpsertOverrideDTO,
    UserAdminDetailResponse,
    UserAdminListResponse,
)


class AdminService:
    def __init__(
        self,
        user_repository: UserRepository,
        account_repository: AccountRepository,
        token_usage_repository: IaTokenUsageRepository | None = None,
        feature_flag_repository: FeatureFlagRepository | None = None,
    ):
        self.user_repository = user_repository
        self.account_repository = account_repository
        self.token_usage_repository = token_usage_repository
        self.feature_flag_repository = feature_flag_repository

    def list_users(self, page: int, page_size: int) -> PaginatedUsersResponse:
        items, total = self.user_repository.find_paginated(page, page_size)
        return PaginatedUsersResponse(
            items=[UserAdminListResponse.model_validate(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_user(self, code: UUID) -> UserAdminDetailResponse:
        user = self.user_repository.find_by_code(code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado",
            )

        detail = UserAdminDetailResponse.model_validate(user)

        account = self.account_repository.find_account_by_user(user.id)
        if account:
            detail.account = AccountSummary.model_validate(account)
            members_raw = self.account_repository.list_members(account.id)
            detail.members = []
            for m in members_raw:
                member_user = self.user_repository.find_by_code(m.user.code) if m.user else None
                if member_user:
                    detail.members.append(
                        AccountMemberSummary(
                            code=member_user.code,
                            name=member_user.name,
                            email=member_user.email,
                            role=m.role.value,
                            is_accepted=m.is_accepted,
                        )
                    )

        return detail

    def create_user(self, dto: CreateUserAdminDTO) -> UserAdminListResponse:
        if self.user_repository.find_by_email(dto.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="E-mail já cadastrado",
            )

        try:
            user_type = UserType[dto.type.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Tipo inválido: {dto.type}. Use 'user' ou 'admin'.",
            )

        try:
            user = self.user_repository.create({
                "name": dto.name,
                "email": dto.email,
                "password": hash_password(dto.password),
                "type": user_type,
                "is_active": True,
            })
            return UserAdminListResponse.model_validate(user)
        except Exception as e:
            logger.error(f"Erro ao criar usuário pelo admin: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar usuário",
            )

    def update_user(self, code: UUID, dto: UpdateUserAdminDTO) -> UserAdminListResponse:
        user = self.user_repository.find_by_code(code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado",
            )

        updates = {}
        if dto.name is not None:
            updates["name"] = dto.name
        if dto.email is not None:
            existing = self.user_repository.find_by_email(dto.email)
            if existing and existing.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="E-mail já em uso por outro usuário",
                )
            updates["email"] = dto.email

        updated = self.user_repository.update(user, updates)
        return UserAdminListResponse.model_validate(updated)

    def deactivate_user(self, code: UUID) -> UserAdminListResponse:
        user = self.user_repository.find_by_code(code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado",
            )

        user.is_active = False
        self.user_repository.update(user, {})
        return UserAdminListResponse.model_validate(user)

    def reactivate_user(self, code: UUID) -> UserAdminListResponse:
        user = self.user_repository.find_by_code(code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado",
            )

        user.is_active = True
        self.user_repository.update(user, {})
        return UserAdminListResponse.model_validate(user)

    def delete_user(self, code: UUID) -> None:
        user = self.user_repository.find_by_code(code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado",
            )

        try:
            self.user_repository.hard_delete(user)
        except Exception as e:
            logger.error(f"Erro ao deletar usuário {code}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao remover usuário",
            )

    # ── Token Usage ──────────────────────────────────────────

    def _require_token_usage_repo(self) -> IaTokenUsageRepository:
        if not self.token_usage_repository:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Repositório de token usage não disponível",
            )
        return self.token_usage_repository

    def list_token_usage_aggregated(
        self,
        account_code: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[TokenUsageAggregatedResponse]:
        repo = self._require_token_usage_repo()
        from uuid import UUID as PyUUID

        parsed_code = PyUUID(account_code) if account_code else None
        rows = repo.list_aggregated(parsed_code, start_date, end_date)
        return [TokenUsageAggregatedResponse(**row) for row in rows]

    def list_token_usage_by_account(
        self, account_code: str, page: int, page_size: int
    ) -> PaginatedTokenUsageResponse:
        repo = self._require_token_usage_repo()
        from uuid import UUID as PyUUID


        account = self.account_repository.find_by_code(PyUUID(account_code))
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        items, total = repo.list_by_account(account.id, page, page_size)
        return PaginatedTokenUsageResponse(
            items=[TokenUsageDetailResponse.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    # ── Feature Flags ─────────────────────────────────────────

    def _require_flag_repo(self) -> FeatureFlagRepository:
        if not self.feature_flag_repository:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Repositório de feature flags não disponível",
            )
        return self.feature_flag_repository

    def list_feature_flags(self) -> list[FeatureFlagAdminResponse]:
        repo = self._require_flag_repo()
        flags = repo.list_all()
        return [
            FeatureFlagAdminResponse(
                name=f.name,
                description=f.description,
                enabled_global=f.enabled_global,
                override_count=len(f.overrides) if f.overrides else 0,
            )
            for f in flags
        ]

    def update_feature_flag(self, name: str, dto: UpdateFeatureFlagDTO) -> FeatureFlagAdminResponse:
        repo = self._require_flag_repo()
        flag = repo.update_global(name, dto.enabled_global)
        if not flag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature flag '{name}' não encontrada",
            )
        return FeatureFlagAdminResponse(
            name=flag.name,
            description=flag.description,
            enabled_global=flag.enabled_global,
            override_count=len(flag.overrides) if flag.overrides else 0,
        )

    def list_flag_overrides(self, flag_name: str) -> list[AccountFeatureFlagResponse]:
        repo = self._require_flag_repo()
        overrides = repo.list_overrides(flag_name)
        result = []
        for o in overrides:
            account = self.account_repository.find_by_id(o.account_id)
            result.append(
                AccountFeatureFlagResponse(
                    account_code=str(account.code) if account else str(o.account_id),
                    account_name=account.name if account else None,
                    flag_name=o.flag_name,
                    enabled=o.enabled,
                )
            )
        return result

    def upsert_flag_override(
        self, flag_name: str, account_code: str, dto: UpsertOverrideDTO
    ) -> AccountFeatureFlagResponse:
        from uuid import UUID as PyUUID

        repo = self._require_flag_repo()
        account = self.account_repository.find_by_code(PyUUID(account_code))
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        override = repo.upsert_override(account.id, flag_name, dto.enabled)
        return AccountFeatureFlagResponse(
            account_code=str(account.code),
            account_name=account.name,
            flag_name=override.flag_name,
            enabled=override.enabled,
        )

    def delete_flag_override(self, flag_name: str, account_code: str) -> None:
        from uuid import UUID as PyUUID

        repo = self._require_flag_repo()
        account = self.account_repository.find_by_code(PyUUID(account_code))
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta não encontrada",
            )
        repo.delete_override(account.id, flag_name)
