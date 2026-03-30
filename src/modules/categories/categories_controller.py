from uuid import UUID

from fastapi import APIRouter, Depends, status, HTTPException
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.dependencies import get_current_account_id
from src.modules.categories.categories_service import CategoriesService
from .dtos import CreateCategoryDTO, UpdateCategoryDTO, CategoryResponse

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get(
    "/",
    response_model=list[CategoryResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista as categorias do usuário"
)
@inject
async def list_categories(
    account_id: int = Depends(get_current_account_id),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    return service.find_all(account_id)


@router.post(
    "/",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma nova categoria"
)
@inject
async def create_category(
    body: CreateCategoryDTO,
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service]),
):
    return service.create(current_user["uid"], account_id, body)


@router.put(
    "/{code}",
    response_model=CategoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza uma categoria"
)
@inject
async def update_category(
    code: UUID,
    body: UpdateCategoryDTO,
    account_id: int = Depends(get_current_account_id),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    return service.update(account_id, code, body)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma categoria (soft delete)"
)
@inject
async def delete_category(
    code: UUID,
    account_id: int = Depends(get_current_account_id),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    service.remove(account_id, code)
