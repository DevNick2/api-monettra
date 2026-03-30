from fastapi import APIRouter, Depends
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.modules.accounts.accounts_service import AccountsService
from .dtos import CreateAccountDTO, InviteMemberDTO, AccountResponse

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("/", response_model=AccountResponse, status_code=201)
@inject
async def create_account(
    body: CreateAccountDTO,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.create_account(current_user["uid"], body)


@router.get("/me", response_model=AccountResponse)
@inject
async def get_my_account(
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.get_my_account(current_user["uid"])


@router.post("/invite", status_code=200)
@inject
async def invite_member(
    body: InviteMemberDTO,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.invite_member(current_user["uid"], body)


@router.delete("/members/{member_user_code}", status_code=200)
@inject
async def remove_member(
    member_user_code: str,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.remove_member(current_user["uid"], member_user_code)
