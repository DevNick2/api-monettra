from uuid import UUID

from fastapi import APIRouter, Depends, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
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
    current_user: dict = Depends(get_current_user),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    return service.find_all(current_user["uid"])


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
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    return service.create(current_user["uid"], body)


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
    current_user: dict = Depends(get_current_user),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    return service.update(current_user["uid"], code, body)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma categoria (soft delete)"
)
@inject
async def delete_category(
    code: UUID,
    current_user: dict = Depends(get_current_user),
    service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    service.remove(current_user["uid"], code)
