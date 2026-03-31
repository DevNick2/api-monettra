"""
CreditCardsService — Regras de negócio do módulo de Cartões de Crédito.

Motor de Fatura (Invoice Engine):
  - Compra no DIA do fechamento → Fatura do MÊS ATUAL.
  - Compra APÓS o dia do fechamento → Fatura do MÊS SEGUINTE.
  - Parcelamento: picota em N installments distribuídas nas faturas consecutivas.
  - Rateio de centavos: diferença acumulada na PRIMEIRA parcela para não perder 1 centavo.
"""

import calendar
from datetime import date
from uuid import UUID

from fastapi import HTTPException, status

from src.repository.credit_card_repository import CreditCardRepository
from src.repository.transaction_repository import TransactionRepository
from src.schemas.credit_cards import CreditCardSchema, InvoiceSchema
from src.schemas.transactions import TransactionType, TransactionClassification
from src.shared.services.redis_service import RedisService
from src.shared.utils.logger import logger
from .dtos import (
    CreateCreditCardDTO,
    UpdateCreditCardDTO,
    CreditCardResponse,
    CreateCreditCardChargeDTO,
    InvoiceResponse,
    InvoiceTransactionItem,
)


class CreditCardsService:
    def __init__(
        self,
        repository: CreditCardRepository,
        transaction_repository: TransactionRepository,
        cache: RedisService,
    ):
        self.repository = repository
        self.transaction_repository = transaction_repository
        self.cache = cache

    # ─── CRUD de Cartões ───────────────────────────────────────────────────────

    def find_all(self, account_id: int) -> list[CreditCardResponse]:
        cards = self.repository.find_all_by_account(account_id)
        return [CreditCardResponse.model_validate(c) for c in cards]

    def create(
        self, user_id: int, account_id: int, payload: CreateCreditCardDTO
    ) -> CreditCardResponse:
        try:
            card = self.repository.create({
                "name": payload.name,
                "credit_limit": payload.credit_limit,
                "closing_day": payload.closing_day,
                "due_day": payload.due_day,
                "user_id": user_id,
                "account_id": account_id,
            })
            return CreditCardResponse.model_validate(card)
        except Exception as e:
            logger.error(f"Erro ao criar cartão: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar cartão de crédito",
            )

    def update(
        self, account_id: int, card_code: UUID, payload: UpdateCreditCardDTO
    ) -> CreditCardResponse:
        card = self.repository.find_by_code(card_code, account_id)
        if not card:
            raise HTTPException(status_code=404, detail="Cartão não encontrado")

        if payload.name is not None:
            card.name = payload.name
        if payload.credit_limit is not None:
            card.credit_limit = payload.credit_limit
        if payload.closing_day is not None:
            card.closing_day = payload.closing_day
        if payload.due_day is not None:
            card.due_day = payload.due_day

        updated = self.repository.update(card)
        return CreditCardResponse.model_validate(updated)

    def remove(self, account_id: int, card_code: UUID) -> None:
        card = self.repository.find_by_code(card_code, account_id)
        if not card:
            raise HTTPException(status_code=404, detail="Cartão não encontrado")
        self.repository.soft_delete(card)

    # ─── Faturas ───────────────────────────────────────────────────────────────

    def find_invoices(self, account_id: int, card_code: UUID) -> list[InvoiceResponse]:
        card = self.repository.find_by_code(card_code, account_id)
        if not card:
            raise HTTPException(status_code=404, detail="Cartão não encontrado")

        invoices = self.repository.find_invoices_by_card(card.id)
        return [self._build_invoice_response(inv, card) for inv in invoices]

    def pay_invoice(self, account_id: int, invoice_code: UUID) -> InvoiceResponse:
        """
        Varre silenciosamente todas as transações-filha da fatura
        e marca cada uma como is_paid = True. Fecha a fatura.
        """
        invoice = self.repository.find_invoice_by_code(invoice_code, account_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Fatura não encontrada")

        if invoice.is_paid:
            raise HTTPException(status_code=409, detail="Fatura já está paga")

        try:
            for transaction in invoice.transactions:
                if not transaction.is_paid:
                    transaction.is_paid = True
                    from datetime import datetime
                    transaction.paid_at = datetime.utcnow()

            self.repository.mark_invoice_paid(invoice)
            self.cache.delete_pattern(
                f"transactions:aid:{invoice.credit_card.account_id}:*"
            )
            return self._build_invoice_response(invoice, invoice.credit_card)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao pagar fatura: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao pagar fatura")

    # ─── Lançamento no Cartão (Motor de Fatura) ────────────────────────────────

    def create_charge(
        self,
        user_id: int,
        account_id: int,
        payload: CreateCreditCardChargeDTO,
        category_id: int | None,
    ) -> list[InvoiceResponse]:
        """
        Cria N parcelas de uma compra no cartão e aloca cada uma na fatura correta.
        Retorna as faturas impactadas.
        """
        card = self.repository.find_by_code(payload.credit_card_code, account_id)

        if not card:
            raise HTTPException(status_code=404, detail="Cartão não encontrado")

        total_cents = payload.amount
        # XXX FIXME :: esse n aqui é tenso
        # Essa variavel poderia ser chamada de installment_count ou
        # installment_quantity ou installment_number
        n = payload.installments

        # Rateio sem perda de centavos: primeira parcela absorve o restante
        base_installment = total_cents // n
        remainder = total_cents - (base_installment * n)

        affected_invoice_ids: set[int] = set()

        try:
            for i in range(n):
                installment_amount = base_installment + (remainder if i == 0 else 0)
                target_month, target_year = self._resolve_invoice_cycle(
                    payload.purchase_date, card.closing_day, offset_months=i
                )
                invoice = self.repository.get_or_create_invoice(
                    card.id, target_month, target_year
                )

                installment_label = f"{i + 1}/{n}" if n > 1 else None
                title = (
                    f"{payload.title} ({installment_label})"
                    if installment_label
                    else payload.title
                )

                # Data de vencimento da parcela = dia de vencimento do cartão no mês alvo
                last_day = calendar.monthrange(target_year, target_month)[1]
                due_day = min(card.due_day, last_day)
                due_date = date(target_year, target_month, due_day)

                self.transaction_repository.create({
                    "title": title,
                    "amount": installment_amount,
                    "type": TransactionType.EXPENSE,
                    "due_date": due_date,
                    "description": payload.description,
                    "type_of_transaction": TransactionClassification.CREDIT_CARD,
                    "is_paid": False,
                    "paid_at": None,
                    "user_id": user_id,
                    "created_by": user_id,
                    "account_id": account_id,
                    "category_id": category_id,
                    "subscription_id": None,
                    "invoice_id": invoice.id,
                })

                invoice.total_amount += installment_amount
                affected_invoice_ids.add(invoice.id)

            self.repository.update(card)
            self.cache.delete_pattern(f"transactions:aid:{account_id}:*")

            invoices = [
                self.repository.find_invoice(card.id, m, y)
                for (m, y) in self._get_affected_months(
                    payload.purchase_date, card.closing_day, n
                )
                if self.repository.find_invoice(card.id, m, y)
            ]
            return [self._build_invoice_response(inv, card) for inv in invoices if inv]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao criar lançamento no cartão: {e}")
            raise HTTPException(
                status_code=500,
                detail="Erro interno ao registrar compra no cartão",
            )

    # ─── Helpers Privados ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_invoice_cycle(
        purchase_date: date, closing_day: int, offset_months: int = 0
    ) -> tuple[int, int]:
        """
        Determina o mês/ano da fatura para uma data de compra.

        Regra: compra NO DIA do fechamento → fatura do mês atual.
               compra APÓS o dia do fechamento → fatura do mês seguinte.
        """
        if purchase_date.day <= closing_day:
            base_month = purchase_date.month
            base_year = purchase_date.year
        else:
            if purchase_date.month == 12:
                base_month = 1
                base_year = purchase_date.year + 1
            else:
                base_month = purchase_date.month + 1
                base_year = purchase_date.year

        # Avançar `offset_months` meses
        total_months = (base_year * 12 + base_month - 1) + offset_months
        target_year = total_months // 12
        target_month = total_months % 12 + 1
        return target_month, target_year

    @staticmethod
    def _get_affected_months(
        purchase_date: date, closing_day: int, n: int
    ) -> list[tuple[int, int]]:
        result = []
        for i in range(n):
            if purchase_date.day <= closing_day:
                base_month = purchase_date.month
                base_year = purchase_date.year
            else:
                if purchase_date.month == 12:
                    base_month = 1
                    base_year = purchase_date.year + 1
                else:
                    base_month = purchase_date.month + 1
                    base_year = purchase_date.year

            total_months = (base_year * 12 + base_month - 1) + i
            target_year = total_months // 12
            target_month = total_months % 12 + 1
            result.append((target_month, target_year))
        return result

    @staticmethod
    def _build_invoice_response(
        invoice: InvoiceSchema, card: CreditCardSchema
    ) -> InvoiceResponse:
        items = [
            InvoiceTransactionItem(
                code=t.code,
                title=t.title,
                amount=t.amount,
                due_date=t.due_date,
                is_paid=t.is_paid,
                description=t.description,
            )
            for t in invoice.transactions
            if t.deleted_at is None
        ]
        return InvoiceResponse(
            code=invoice.code,
            reference_month=invoice.reference_month,
            reference_year=invoice.reference_year,
            total_amount=invoice.total_amount,
            is_paid=invoice.is_paid,
            credit_card_code=card.code,
            credit_card_name=card.name,
            transactions=items,
            created_at=invoice.created_at,
        )
