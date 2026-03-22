from uuid import UUID

from fastapi import APIRouter, Depends, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.modules.subscriptions.subscriptions_service import SubscriptionsService
from .dtos import CreateSubscriptionDTO, UpdateSubscriptionDTO, SubscriptionResponse

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get(
    "/",
    response_model=list[SubscriptionResponse],
    summary="Lista as assinaturas do usuário autenticado",
)
@inject
async def list_subscriptions(
    current_user: dict = Depends(get_current_user),
    service: SubscriptionsService = Depends(Provide[ContainerService.subscriptions_service]),
):
    return service.find_all(current_user["uid"])


@router.get(
    "/active",
    response_model=list[SubscriptionResponse],
    summary="Lista apenas as assinaturas ativas do usuário",
)
@inject
async def list_active_subscriptions(
    current_user: dict = Depends(get_current_user),
    service: SubscriptionsService = Depends(Provide[ContainerService.subscriptions_service]),
):
    return service.find_active(current_user["uid"])


@router.post(
    "/",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma nova assinatura",
)
@inject
async def create_subscription(
    body: CreateSubscriptionDTO,
    current_user: dict = Depends(get_current_user),
    service: SubscriptionsService = Depends(Provide[ContainerService.subscriptions_service]),
):
    return service.create(current_user["uid"], body)


@router.patch(
    "/{code}/toggle",
    response_model=SubscriptionResponse,
    summary="Ativa ou desativa uma assinatura",
)
@inject
async def toggle_subscription(
    code: UUID,
    current_user: dict = Depends(get_current_user),
    service: SubscriptionsService = Depends(Provide[ContainerService.subscriptions_service]),
):
    return service.toggle_active(current_user["uid"], code)


@router.put(
    "/{code}",
    response_model=SubscriptionResponse,
    summary="Atualiza uma assinatura",
)
@inject
async def update_subscription(
    code: UUID,
    body: UpdateSubscriptionDTO,
    current_user: dict = Depends(get_current_user),
    service: SubscriptionsService = Depends(Provide[ContainerService.subscriptions_service]),
):
    return service.update(current_user["uid"], code, body)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma assinatura (soft delete)",
)
@inject
async def delete_subscription(
    code: UUID,
    current_user: dict = Depends(get_current_user),
    service: SubscriptionsService = Depends(Provide[ContainerService.subscriptions_service]),
):
    service.remove(current_user["uid"], code)
