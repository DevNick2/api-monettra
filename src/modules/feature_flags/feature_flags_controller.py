from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.repository.feature_flag_repository import FeatureFlagRepository
from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.dependencies import get_current_account_id

router = APIRouter(prefix="/feature-flags", tags=["Feature Flags"])


@router.get(
    "/{name}/me",
    summary="Retorna se uma feature flag está habilitada para a conta autenticada",
)
@inject
async def flag_enabled_for_me(
    name: str,
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    repo: FeatureFlagRepository = Depends(Provide[ContainerService.feature_flag_repository]),
):
    enabled = repo.enabled_for_account(name, account_id)
    return {"name": name, "enabled": enabled}
