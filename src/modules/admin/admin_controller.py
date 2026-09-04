from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status

from src.modules.admin.admin_service import AdminService
from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import require_admin_scope

from .dtos import (
    AccountFeatureFlagResponse,
    CreateUserAdminDTO,
    FeatureFlagAdminResponse,
    PaginatedTokenUsageResponse,
    PaginatedUsersResponse,
    TokenUsageAggregatedResponse,
    UpdateFeatureFlagDTO,
    UpdateUserAdminDTO,
    UpsertOverrideDTO,
    UserAdminDetailResponse,
    UserAdminListResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/users",
    response_model=PaginatedUsersResponse,
    summary="Lista usuários com paginação",
)
@inject
async def list_users(
    page: int = 1,
    page_size: int = 20,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.list_users(page, page_size)


@router.get(
    "/users/{code}",
    response_model=UserAdminDetailResponse,
    summary="Retorna detalhes de um usuário com conta e membros",
)
@inject
async def get_user(
    code: UUID,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.get_user(code)


@router.post(
    "/users",
    response_model=UserAdminListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um novo usuário pelo painel admin",
)
@inject
async def create_user(
    body: CreateUserAdminDTO,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.create_user(body)


@router.patch(
    "/users/{code}",
    response_model=UserAdminListResponse,
    summary="Atualiza nome e/ou e-mail de um usuário",
)
@inject
async def update_user(
    code: UUID,
    body: UpdateUserAdminDTO,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.update_user(code, body)


@router.patch(
    "/users/{code}/deactivate",
    response_model=UserAdminListResponse,
    summary="Desativa um usuário (is_active = False)",
)
@inject
async def deactivate_user(
    code: UUID,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.deactivate_user(code)


@router.patch(
    "/users/{code}/reactivate",
    response_model=UserAdminListResponse,
    summary="Reativa um usuário (is_active = True)",
)
@inject
async def reactivate_user(
    code: UUID,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.reactivate_user(code)


@router.delete(
    "/users/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard delete de usuário com cascata de AccountMember",
)
@inject
async def delete_user(
    code: UUID,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    service.delete_user(code)


# ── Token Usage ──────────────────────────────────────────────


@router.get(
    "/token-usage",
    response_model=list[TokenUsageAggregatedResponse],
    summary="Consumo agregado de tokens de IA por conta",
)
@inject
async def list_token_usage(
    account_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    from datetime import datetime

    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    return service.list_token_usage_aggregated(account_code, start, end)


@router.get(
    "/token-usage/{account_code}",
    response_model=PaginatedTokenUsageResponse,
    summary="Log detalhado de chamadas de IA por conta",
)
@inject
async def list_token_usage_by_account(
    account_code: str,
    page: int = 1,
    page_size: int = 20,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.list_token_usage_by_account(account_code, page, page_size)


# ── Feature Flags ─────────────────────────────────────────────


@router.get(
    "/feature-flags",
    response_model=list[FeatureFlagAdminResponse],
    summary="Lista todas as feature flags com contagem de overrides",
)
@inject
async def list_feature_flags(
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.list_feature_flags()


@router.patch(
    "/feature-flags/{name}",
    response_model=FeatureFlagAdminResponse,
    summary="Altera enabled_global de uma feature flag",
)
@inject
async def update_feature_flag(
    name: str,
    body: UpdateFeatureFlagDTO,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.update_feature_flag(name, body)


@router.get(
    "/feature-flags/{name}/accounts",
    response_model=list[AccountFeatureFlagResponse],
    summary="Lista overrides por conta para uma feature flag",
)
@inject
async def list_flag_overrides(
    name: str,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.list_flag_overrides(name)


@router.put(
    "/feature-flags/{name}/accounts/{account_code}",
    response_model=AccountFeatureFlagResponse,
    summary="Upsert de override de feature flag por conta",
)
@inject
async def upsert_flag_override(
    name: str,
    account_code: str,
    body: UpsertOverrideDTO,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    return service.upsert_flag_override(name, account_code, body)


@router.delete(
    "/feature-flags/{name}/accounts/{account_code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove override de feature flag de uma conta",
)
@inject
async def delete_flag_override(
    name: str,
    account_code: str,
    _: dict = Depends(require_admin_scope),
    service: AdminService = Depends(Provide[ContainerService.admin_service]),
):
    service.delete_flag_override(name, account_code)
