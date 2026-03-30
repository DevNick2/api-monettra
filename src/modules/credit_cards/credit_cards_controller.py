from uuid import UUID

from fastapi import APIRouter, Depends, status
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.dependencies import get_current_account_id
from src.modules.categories.categories_service import CategoriesService
from src.modules.credit_cards.credit_cards_service import CreditCardsService
from .dtos import (
    CreateCreditCardDTO,
    UpdateCreditCardDTO,
    CreditCardResponse,
    CreateCreditCardChargeDTO,
    InvoiceResponse,
)

router = APIRouter(prefix="/credit-cards", tags=["Credit Cards"])


@router.get(
    "/",
    response_model=list[CreditCardResponse],
    summary="Lista os cartões de crédito da conta",
)
@inject
async def list_credit_cards(
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
):
    return service.find_all(account_id)


@router.post(
    "/",
    response_model=CreditCardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um novo cartão de crédito",
)
@inject
async def create_credit_card(
    payload: CreateCreditCardDTO,
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
):
    return service.create(current_user["uid"], account_id, payload)


@router.put(
    "/{code}",
    response_model=CreditCardResponse,
    summary="Atualiza um cartão de crédito",
)
@inject
async def update_credit_card(
    code: UUID,
    payload: UpdateCreditCardDTO,
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
):
    return service.update(account_id, code, payload)


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um cartão de crédito (soft delete)",
)
@inject
async def delete_credit_card(
    code: UUID,
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
):
    service.remove(account_id, code)


@router.get(
    "/{card_code}/invoices",
    response_model=list[InvoiceResponse],
    summary="Lista as faturas de um cartão",
)
@inject
async def list_invoices(
    card_code: UUID,
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
):
    return service.find_invoices(account_id, card_code)


@router.post(
    "/charge",
    response_model=list[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma compra no cartão (com suporte a parcelamento)",
)
@inject
async def create_charge(
    payload: CreateCreditCardChargeDTO,
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
    categories_service: CategoriesService = Depends(Provide[ContainerService.categories_service]),
):
    category_id: int | None = None
    if payload.category_code:
        cat = categories_service.show(payload.category_code, current_user["uid"])
        category_id = cat.id if cat else None

    return service.create_charge(current_user["uid"], account_id, payload, category_id)


@router.patch(
    "/invoices/{invoice_code}/pay",
    response_model=InvoiceResponse,
    summary="Paga uma fatura — marca todas as transações-filha como pagas",
)
@inject
async def pay_invoice(
    invoice_code: UUID,
    account_id: int = Depends(get_current_account_id),
    service: CreditCardsService = Depends(Provide[ContainerService.credit_cards_service]),
):
    return service.pay_invoice(account_id, invoice_code)
