from fastapi import APIRouter, Depends
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user, require_admin
from src.modules.users.users_service import UsersService
from src.modules.users.dtos import UpdateUserDTO, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=list[UserResponse], summary="Lista todos os usuários (admin)")
@inject
async def list_users(
    current_user: dict = Depends(require_admin),
    service: UsersService = Depends(Provide[ContainerService.users_service]),
):
    return service.find_all()


@router.patch("/{user_code}", response_model=UserResponse, summary="Atualiza dados de um usuário")
@inject
async def update_user(
    user_code: str,
    payload: UpdateUserDTO,
    current_user: dict = Depends(get_current_user),
    service: UsersService = Depends(Provide[ContainerService.users_service]),
):
    return service.update(user_code, payload, current_user)


@router.patch(
    "/{user_code}/deactivate",
    response_model=UserResponse,
    summary="Desativa um usuário (admin)",
)
@inject
async def deactivate_user(
    user_code: str,
    current_user: dict = Depends(require_admin),
    service: UsersService = Depends(Provide[ContainerService.users_service]),
):
    return service.deactivate(user_code)
