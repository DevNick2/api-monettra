from datetime import date
from fastapi import APIRouter, Depends, Query, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.dependencies import get_current_account_id
from src.modules.planning.dtos import PlanningEntryResponse
from src.modules.planning.planning_service import PlanningService

from src.modules.categories.categories_service import CategoriesService

router = APIRouter(prefix="/planning", tags=["Planning"])

@router.get("", response_model=list[PlanningEntryResponse])
@inject
async def horizon(
    account_id: int = Depends(get_current_account_id),
    service: PlanningService = Depends(Provide[ContainerService.planning_service])
):
    return service.horizon(account_id)