from datetime import date
from fastapi import APIRouter, Depends, Query, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.modules.planning.dtos import CreatePlanningEntryDTO, UpdatePlanningEntryDTO, PlanningEntryResponse, PlanningHorizonResponse
from src.modules.planning.planning_service import PlanningService

from src.modules.categories.categories_service import CategoriesService

router = APIRouter(prefix="/planning", tags=["Planning"])

@router.post("", response_model=list[PlanningEntryResponse], status_code=status.HTTP_201_CREATED)
@inject
async def create_entry(
    payload: CreatePlanningEntryDTO,
    current_user: dict = Depends(get_current_user),
    service: PlanningService = Depends(Provide[ContainerService.planning_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    category = None
    if payload.category_code:
        category = category_service.show(str(payload.category_code))
        if not category:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

    return service.create(current_user["uid"], payload, category)

@router.get("", response_model=list[PlanningEntryResponse])
@inject
async def find_all(
    start_date: date | None = Query(None, description="Data Inicial"),
    end_date: date | None = Query(None, description="Data Final"),
    current_user: dict = Depends(get_current_user),
    service: PlanningService = Depends(Provide[ContainerService.planning_service])
):
    return service.find_all(current_user["uid"], start_date, end_date)

@router.get("/horizon", response_model=PlanningHorizonResponse)
@inject
async def horizon(
    start_date: date = Query(..., description="Data Inicial"),
    end_date: date = Query(..., description="Data Final"),
    current_user: dict = Depends(get_current_user),
    service: PlanningService = Depends(Provide[ContainerService.planning_service])
):
    return service.horizon(current_user["uid"], start_date, end_date)

@router.put("/{code}", response_model=list[PlanningEntryResponse])
@inject
async def update_entry(
    code: str,
    payload: UpdatePlanningEntryDTO,
    current_user: dict = Depends(get_current_user),
    service: PlanningService = Depends(Provide[ContainerService.planning_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    category = None

    if payload.category_code:
        category = category_service.show(str(payload.category_code))

    return service.update(current_user["uid"], code, payload, category)

@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_entry(
    code: str,
    scope: str = Query("this", description="'this' ou 'this_and_future'"),
    current_user: dict = Depends(get_current_user),
    service: PlanningService = Depends(Provide[ContainerService.planning_service])
):
    service.delete(current_user["uid"], code, scope)

@router.post("/{code}/materialize", response_model=PlanningEntryResponse)
@inject
async def materialize(
    code: str,
    current_user: dict = Depends(get_current_user),
    service: PlanningService = Depends(Provide[ContainerService.planning_service])
):
    return service.materialize(current_user["uid"], code)
