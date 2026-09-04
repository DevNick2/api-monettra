from fastapi import Depends, HTTPException, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user


@inject
def get_current_account_id(
    current_user: dict = Depends(get_current_user),
    accounts_service = Depends(Provide[ContainerService.accounts_service])
) -> int:
    """
    Recupera o ID da conta principal vinculada ao usuário atual.
    Usado como Dependency nos controllers para multi-tenant.
    """
    account = accounts_service.repository.find_account_by_user(current_user["uid"])
    if not account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O usuário não pertence a nenhuma conta compartilhada"
        )
    return account.id
