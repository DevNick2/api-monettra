from fastapi import APIRouter, Depends, HTTPException
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.repository.user_repository import UserRepository
from src.shared.utils.logger import logger

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", summary="Lista todos os usuários")
@inject
async def list_users(
    user_repository: UserRepository = Depends(Provide[ContainerService.userRepository])
):
    try:
        return user_repository.find_all()
    except Exception as e:
        logger.error(f"Erro ao buscar usuários: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar usuários")
