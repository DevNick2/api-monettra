from uuid import UUID

from fastapi import APIRouter, Depends, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.modules.transactions.transactions_service import TransactionsService
from src.modules.categories.categories_service import CategoriesService
from src.schemas.categories import CategorySchema
from .dtos import CreateTransactionDTO, UpdateTransactionDTO, TransactionResponse

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get(
    "/",
    response_model=list[TransactionResponse],
    summary="Lista as transações do usuário autenticado"
)
@inject
async def list_transactions(
    month: int | None = None,
    year: int | None = None,
    current_user: dict = Depends(get_current_user),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.find_all(current_user["uid"], month=month, year=year)


@router.post(
    "/",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma nova transação"
)
@inject
async def create_transaction(
    body: CreateTransactionDTO,
    current_user: dict = Depends(get_current_user),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.create(current_user["uid"], body)


@router.patch(
    "/{code}/pay",
    response_model=TransactionResponse,
    summary="Marca uma transação como paga"
)
@inject
async def pay_transaction(
    code: UUID,
    current_user: dict = Depends(get_current_user),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.mark_as_paid(current_user["uid"], code)


@router.put(
    "/{code}",
    response_model=TransactionResponse,
    summary="Atualiza uma transação"
)
@inject
async def update_transaction(
    code: UUID,
    body: UpdateTransactionDTO,
    current_user: dict = Depends(get_current_user),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    category: CategorySchema | None = None

    if body.category_code is not None:
        category = category_service.show(body.category_code)

    return service.update(current_user["uid"], code, body, category)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma transação (soft delete)"
)
@inject
async def delete_transaction(
    code: UUID,
    current_user: dict = Depends(get_current_user),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    service.remove(current_user["uid"], code)
