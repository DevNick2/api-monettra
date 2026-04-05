from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.dependencies import get_current_account_id
from src.modules.transactions.transactions_service import TransactionsService
from src.modules.categories.categories_service import CategoriesService
from src.schemas.categories import CategorySchema
from .dtos import (
    CreateTransactionDTO,
    BatchCreateTransactionDTO,
    UpdateTransactionDTO,
    TransactionResponse,
    TransactionSummaryResponse,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get(
    "/summary",
    response_model=TransactionSummaryResponse,
    summary="Retorna agregação de receitas, despesas e saldos líquidos do mês"
)
@inject
async def get_transactions_summary(
    month: int | None = None,
    year: int | None = None,
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.get_summary(account_id, month=month, year=year)


@router.get(
    "/",
    response_model=list[TransactionResponse],
    summary="Lista as transações do usuário autenticado"
)
@inject
async def list_transactions(
    month: int | None = None,
    year: int | None = None,
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.find_all(account_id, month=month, year=year)


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
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.create(current_user["uid"], account_id, body)


@router.post(
    "/batch",
    response_model=list[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Cria transações recorrentes em lote (server-side). O backend gera todas as parcelas a partir de start_date até Dezembro."
)
@inject
async def create_batch_transactions(
    body: BatchCreateTransactionDTO,
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.create_batch(current_user["uid"], account_id, body)


@router.patch(
    "/{code}/pay",
    response_model=TransactionResponse,
    summary="Marca uma transação como paga"
)
@inject
async def pay_transaction(
    code: UUID,
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    return service.mark_as_paid(account_id, code)


@router.put(
    "/{code}",
    response_model=TransactionResponse,
    summary="Atualiza uma transação. Suporta propagação via scope=single|forward|all"
)
@inject
async def update_transaction(
    code: UUID,
    body: UpdateTransactionDTO,
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service]),
    category_service: CategoriesService = Depends(Provide[ContainerService.categories_service])
):
    category: CategorySchema | None = None

    if body.category_code is not None:
        category = category_service.show(account_id, body.category_code)

    return service.update(account_id, code, body, category)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma transação (soft delete). scope=single|forward|all controla propagação."
)
@inject
async def delete_transaction(
    code: UUID,
    scope: Literal["single", "forward", "all"] = Query(default="single"),
    account_id: int = Depends(get_current_account_id),
    service: TransactionsService = Depends(Provide[ContainerService.transactions_service])
):
    service.remove(account_id, code, scope=scope)

