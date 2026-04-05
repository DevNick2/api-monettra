"""
TransactionsService — Regras de negócio do módulo de transações.

Cache Redis:
  - find_all  → cacheado por 60s. Chave: "transactions:aid:{account_id}:m:{month}:y:{year}"
  - Qualquer operação de escrita (create, update, remove, mark_as_paid)
    invalida todas as chaves do usuário via padrão "transactions:aid:{account_id}:*"
"""

import json
import uuid
import calendar

from datetime import datetime, timezone, date
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from fastapi import HTTPException, status

from src.repository.transaction_repository import TransactionRepository
from src.shared.services.redis_service import RedisService
from src.shared.utils.logger import logger
from .dtos import (
    CreateTransactionDTO,
    BatchCreateTransactionDTO,
    UpdateTransactionDTO,
    TransactionResponse,
    TransactionSummaryResponse,
)
from src.schemas.transactions import TransactionType
from src.schemas.categories import CategorySchema
from src.schemas.users import UserSchema
from src.schemas.accounts import AccountMemberSchema
from src.shared.services.ia_service import IaService
from sqlalchemy import select


CACHE_TTL = 10  # segundos


def _resolve_paid_status_for_manual_date(transaction_date: date, today_local: date) -> bool:
    """Regra de negócio: lançamentos manuais com data ≤ hoje são marcados como pagos."""
    return transaction_date <= today_local


def _cache_key(account_id: int, month: int | None, year: int | None) -> str:
    return f"transactions:aid:{account_id}:m:{month}:y:{year}"


def _summary_cache_key(account_id: int, month: int | None, year: int | None) -> str:
    return f"transactions:summary:aid:{account_id}:m:{month}:y:{year}"


def _invalidate_account_cache(cache: RedisService, account_id: int) -> None:
    cache.delete_pattern(f"transactions:aid:{account_id}:*")
    cache.delete_pattern(f"transactions:summary:aid:{account_id}:*")


class TransactionsService:
    def __init__(
        self,
        repository: TransactionRepository,
        cache: RedisService,
        ia: IaService
    ):

        self.repository = repository
        self.cache = cache
        self.ia = ia

    def find_all(
        self,
        account_id: int,
        month: int | None = None,
        year: int | None = None,
    ) -> list:
        key = _cache_key(account_id, month, year)
        cached = self.cache.get(key)

        if cached:
            logger.info(f"Cache HIT → {key}")
            raw = json.loads(cached)
            return raw

        logger.info(f"Cache MISS → {key} — buscando no banco")
        results = self.repository.find_all_by_account(
            account_id, month=month, year=year
        )

        try:
            # Converte e garante o relationship manual para formato RAW
            raw_results = []
            for t in results:
                t_dict = {
                    c.name: getattr(t, c.name)
                    for c in t.__table__.columns
                }
                t_dict['category'] = (
                    {
                        c.name: getattr(t.category, c.name)
                        for c in t.category.__table__.columns
                    }
                ) if t.category else None
                t_dict['subscription_payment_method'] = (
                    t.subscription.payment_method.value if t.subscription else None
                )
                t_dict['invoice_code'] = (
                    str(t.invoice.code) if t.invoice else None
                )
                t_dict['invoice_reference_month'] = (
                    t.invoice.reference_month if t.invoice else None
                )
                t_dict['invoice_reference_year'] = (
                    t.invoice.reference_year if t.invoice else None
                )
                t_dict['credit_card_name'] = (
                    t.invoice.credit_card.name if t.invoice and t.invoice.credit_card else None
                )
                t_dict['owner'] = (
                    {
                        "code": str(t.owner.code),
                        "name": t.owner.name,
                        "photo_url": None,
                    }
                    if t.owner else None
                )
                raw_results.append(t_dict)

            serialized = json.dumps(jsonable_encoder(raw_results))
            self.cache.set(key, serialized, ttl=CACHE_TTL)
        except Exception as e:
            logger.warning(f"Falha ao serializar para cache: {e}")

        return results

    def get_summary(
        self,
        account_id: int,
        month: int | None = None,
        year: int | None = None,
    ) -> TransactionSummaryResponse:
        key = _summary_cache_key(account_id, month, year)
        cached = self.cache.get(key)

        if cached:
            logger.info(f"Cache HIT (summary) → {key}")
            return TransactionSummaryResponse(**json.loads(cached))

        logger.info(f"Cache MISS (summary) → {key}")
        data = self.repository.get_summary_by_account(account_id, month=month, year=year)

        try:
            self.cache.set(key, json.dumps(data), ttl=CACHE_TTL)
        except Exception as e:
            logger.warning(f"Falha ao serializar summary para cache: {e}")

        return TransactionSummaryResponse(**data)

    def create(self, user_id: int, account_id: int, data: CreateTransactionDTO):
        if data.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O valor da transação deve ser positivo"
            )

        category_id = self._resolve_category(account_id, data.category_code)
        owner_id = self._resolve_owner(account_id, data.owner_code, default_user_id=user_id)

        is_paid = _resolve_paid_status_for_manual_date(data.due_date, date.today())

        try:
            record = self.repository.create({
                "title": data.title,
                "amount": data.amount,
                "type": TransactionType[data.type.value.upper()],
                "due_date": data.due_date,
                "description": data.description,
                "is_paid": is_paid,
                "paid_at": datetime.now(timezone.utc) if is_paid else None,
                "user_id": user_id,
                "created_by": user_id,
                "account_id": account_id,
                "category_id": category_id,
                "owner_id": owner_id,
            })

            _invalidate_account_cache(self.cache, account_id)
            return record
        except Exception as e:
            logger.error(f"Erro ao criar transação: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar transação"
            )

    def create_batch(
        self,
        user_id: int,
        account_id: int,
        data: BatchCreateTransactionDTO,
    ) -> list:
        """
        Cria um grupo de transações recorrentes partindo da start_date
        até Dezembro do mesmo ano.
        Todas as parcelas compartilham o mesmo recurrence_id.
        """
        if data.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O valor da transação deve ser positivo"
            )

        category_id = self._resolve_category(account_id, data.category_code)
        owner_id = self._resolve_owner(account_id, data.owner_code, default_user_id=user_id)
        recurrence_id = uuid.uuid4()

        start = data.start_date
        records = []
        today_local = date.today()
        for month in range(start.month, 13):
            last_day = calendar.monthrange(start.year, month)[1]
            day = min(start.day, last_day)
            due = date(start.year, month, day)
            is_paid = _resolve_paid_status_for_manual_date(due, today_local)
            records.append({
                "title": data.title,
                "amount": data.amount,
                "type": TransactionType[data.type.value.upper()],
                "due_date": due,
                "description": data.description,
                "is_paid": is_paid,
                "paid_at": (
                    datetime.now(timezone.utc) if is_paid else None
                ),
                "user_id": user_id,
                "created_by": user_id,
                "account_id": account_id,
                "category_id": category_id,
                "recurrence_id": recurrence_id,
                "owner_id": owner_id,
            })

        try:
            result = self.repository.bulk_create(records)
            _invalidate_account_cache(self.cache, account_id)
            return result
        except Exception as e:
            logger.error(f"Erro ao criar transações em lote: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar lote de transações"
            )

    def mark_as_paid(self, account_id: int, transaction_code: UUID):
        transaction = self.repository.find_by_code(
            transaction_code, account_id
        )
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transação não encontrada",
            )

        transaction.is_paid = not transaction.is_paid
        transaction.paid_at = (
            datetime.now(timezone.utc) if transaction.is_paid else None
        )
        result = self.repository.update(transaction)
        _invalidate_account_cache(self.cache, account_id)
        return result

    def update(
        self,
        account_id: int,
        transaction_code: UUID,
        data: UpdateTransactionDTO,
        category: CategorySchema | None
    ):
        transaction = self.repository.find_by_code(
            transaction_code, account_id
        )

        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transação não encontrada",
            )

        scope = data.scope  # "single" | "forward" | "all"

        # Determina quais transações serão afetadas
        targets = [transaction]
        if scope != "single" and transaction.recurrence_id:
            if scope == "forward":
                targets = self.repository.find_by_recurrence_forward(
                    transaction.recurrence_id,
                    account_id,
                    transaction.due_date,
                )
            elif scope == "all":
                targets = self.repository.find_all_by_recurrence(
                    transaction.recurrence_id, account_id
                )

        owner_id = self._resolve_owner(account_id, data.owner_code) if data.owner_code else None

        for t in targets:
            if data.title is not None:
                t.title = data.title
            if data.amount is not None:
                if data.amount <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="O valor da transação deve ser positivo"
                    )
                t.amount = data.amount
            if data.type is not None:
                t.type = TransactionType[data.type.value.upper()]
            if data.description is not None:
                t.description = data.description
            # A data só muda para "single" para preservar datas cronológicas
            if data.due_date is not None and scope == "single":
                t.due_date = data.due_date
                # Recalcula is_paid com base na nova data (regra de lançamento manual)
                auto_paid = _resolve_paid_status_for_manual_date(data.due_date, date.today())
                t.is_paid = auto_paid
                t.paid_at = datetime.now(timezone.utc) if auto_paid else None
            elif data.is_paid is not None:
                t.is_paid = data.is_paid
                t.paid_at = (
                    datetime.now(timezone.utc) if data.is_paid else None
                )
            # Categoria é propagada em todos os escopos
            if category is not None:
                t.category_id = category.id
            # Owner atualizado apenas no escopo "single"
            if owner_id is not None and scope == "single":
                t.owner_id = owner_id

        # Persiste via ORM dirty tracking
        self.repository.update(targets[0])
        if len(targets) > 1:
            self.repository.session.commit()

        _invalidate_account_cache(self.cache, account_id)
        return targets[0]

    def remove(
        self,
        account_id: int,
        transaction_code: UUID,
        scope: str = "single",
    ):
        transaction = self.repository.find_by_code(
            transaction_code, account_id
        )
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transação não encontrada",
            )

        if scope == "single" or not transaction.recurrence_id:
            self.repository.soft_delete(transaction)
        elif scope == "forward":
            targets = self.repository.find_by_recurrence_forward(
                transaction.recurrence_id,
                account_id,
                transaction.due_date,
            )
            self.repository.bulk_soft_delete(targets)
        elif scope == "all":
            targets = self.repository.find_all_by_recurrence(
                transaction.recurrence_id, account_id
            )
            self.repository.bulk_soft_delete(targets)

        _invalidate_account_cache(self.cache, account_id)

    def _resolve_category(
        self,
        account_id: int,
        category_code,
    ) -> int | None:
        """Resolve o category_code para o ID interno, ou None."""
        if not category_code:
            return None
        result = self.repository.session.execute(
            select(CategorySchema)
            .where(CategorySchema.code == category_code)
            .where(CategorySchema.account_id == account_id)
            .where(CategorySchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada"
            )
        return result.id

    def _resolve_owner(
        self,
        account_id: int,
        owner_code,
        default_user_id: int | None = None,
    ) -> int | None:
        """
        Resolve o owner_code (UUID público) para o ID interno do usuário.
        Valida que o usuário é membro da conta.
        Se owner_code for None, retorna default_user_id (ou None).
        """
        if not owner_code:
            return default_user_id

        result = self.repository.session.execute(
            select(UserSchema)
            .join(AccountMemberSchema, AccountMemberSchema.user_id == UserSchema.id)
            .where(UserSchema.code == owner_code)
            .where(AccountMemberSchema.account_id == account_id)
            .where(AccountMemberSchema.is_accepted == True)  # noqa: E712
            .where(AccountMemberSchema.deleted_at == None)  # noqa: E711
            .where(UserSchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dono da transação não encontrado ou não é membro desta conta"
            )
        return result.id
