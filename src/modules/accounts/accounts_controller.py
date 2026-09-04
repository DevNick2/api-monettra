from fastapi import APIRouter, Depends, Request
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.rate_limit import rate_limit
from src.modules.accounts.accounts_service import AccountsService
from .dtos import (
    AccountResponse,
    CreateAccountDTO,
    InviteMemberDTO,
    InviteResponse,
    RegisterViaInviteDTO,
)

router = APIRouter(prefix="/accounts", tags=["Accounts"])
invite_router = APIRouter(prefix="/invite", tags=["Invite"])


# ─────────────────────────────────────────────
# Conta (autenticados)
# ─────────────────────────────────────────────

@router.post("/", response_model=AccountResponse, status_code=201)
@inject
async def create_account(
    payload: CreateAccountDTO,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.create_account(current_user["uid"], payload)


@router.get("/me", response_model=AccountResponse)
@inject
async def get_my_account(
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.get_my_account(current_user["uid"])


@router.delete("/members/{member_user_code}", status_code=200)
@inject
async def remove_member(
    member_user_code: str,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.remove_member(current_user["uid"], member_user_code)


# ─────────────────────────────────────────────
# Convites (autenticados — OWNER)
# ─────────────────────────────────────────────

@router.post("/invite", response_model=InviteResponse, status_code=201)
@inject
async def send_invite(
    payload: InviteMemberDTO,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.send_invite(current_user["uid"], payload)


@router.get("/invites", response_model=list[InviteResponse])
@inject
async def list_invites(
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.list_invites(current_user["uid"])


@router.post("/invites/{invite_code}/resend", response_model=InviteResponse)
@inject
async def resend_invite(
    invite_code: str,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.resend_invite(current_user["uid"], invite_code)


@router.delete("/invites/{invite_code}", status_code=200)
@inject
async def revoke_invite(
    invite_code: str,
    current_user: dict = Depends(get_current_user),
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    return service.revoke_invite(current_user["uid"], invite_code)


# ─────────────────────────────────────────────
# Convites (públicos — sem autenticação)
# ─────────────────────────────────────────────

@invite_router.get("/{token}", response_model=InviteResponse)
@inject
async def validate_invite(
    token: str,
    request: Request,
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    rate_limit(request, key=f"invite_validate:{token}", max_requests=10, window_seconds=60)
    return service.validate_invite_token(token)


@invite_router.post("/{token}/register", status_code=201)
@inject
async def register_via_invite(
    token: str,
    payload: RegisterViaInviteDTO,
    request: Request,
    service: AccountsService = Depends(Provide[ContainerService.accounts_service]),
):
    rate_limit(request, key=f"invite_register:{request.client.host}", max_requests=5, window_seconds=300)
    return service.register_via_invite(token, payload)
