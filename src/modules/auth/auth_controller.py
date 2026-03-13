from fastapi import APIRouter, Depends
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.modules.auth.auth_service import AuthService
from .dtos import RegisterDTO, LoginDTO, TokenResponse, UserResponse
from src.schemas.categories import DEFAULT_CATEGORIES
from src.modules.categories.categories_service import CategoriesService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Cadastra um novo usuário"
)
@inject
async def register(
    body: RegisterDTO,
    service: AuthService = Depends(Provide[ContainerService.auth_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    newUser = service.register(body)

    defaultCategories = DEFAULT_CATEGORIES

    category_service.create_in_lot(newUser.id, defaultCategories)

    return newUser


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autentica o usuário e retorna um JWT"
)
@inject
async def login(
    body: LoginDTO,
    service: AuthService = Depends(Provide[ContainerService.auth_service])
):
    return service.login(body)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retorna os dados do usuário autenticado"
)
@inject
async def me(
    current_user: dict = Depends(get_current_user),
    service: AuthService = Depends(Provide[ContainerService.auth_service])
):
    return service.get_by_code(current_user["sub"])
