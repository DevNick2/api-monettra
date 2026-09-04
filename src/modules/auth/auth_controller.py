from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.modules.accounts.accounts_service import AccountsService
from src.modules.accounts.dtos import CreateAccountDTO
from src.modules.auth.auth_service import AuthService
from src.modules.categories.categories_service import CategoriesService
from src.schemas.categories import DEFAULT_CATEGORIES
from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user

from .dtos import GoogleCallbackDTO, LoginDTO, RegisterDTO, TokenResponse, UserResponse

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
    accounts_service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    newUser = service.register(body)

    # Criar Account pessoal automaticamente para o novo usuário
    accounts_service.create_account(
        newUser.id,
        CreateAccountDTO(name=f"Conta de {newUser.name or newUser.email}")
    )
    account_id = accounts_service.repository.find_account_by_user(newUser.id).id

    defaultCategories = DEFAULT_CATEGORIES
    category_service.create_in_lot(newUser.id, account_id, defaultCategories)

    return newUser


@router.post(
    "/google/callback",
    response_model=TokenResponse,
    summary="Autentica via Google OAuth e retorna JWT"
)
@inject
async def google_callback(
    body: GoogleCallbackDTO,
    service: AuthService = Depends(Provide[ContainerService.auth_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service]),
    accounts_service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.google_login(
        body=body,
        category_service=category_service,
        accounts_service=accounts_service,
    )


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


@router.post(
    "/admin/login",
    response_model=TokenResponse,
    summary="Autentica um administrador e retorna JWT com scope admin"
)
@inject
async def admin_login(
    body: LoginDTO,
    service: AuthService = Depends(Provide[ContainerService.auth_service])
):
    return service.admin_login(body)


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
