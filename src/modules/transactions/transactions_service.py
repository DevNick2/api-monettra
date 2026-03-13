"""
TransactionsService — Regras de negócio do módulo de transações.

Cache Redis:
  - find_all  → cacheado por 60s. Chave: "transactions:uid:{user_id}:m:{month}:y:{year}"
  - Qualquer operação de escrita (create, update, remove, mark_as_paid)
    invalida todas as chaves do usuário via padrão "transactions:uid:{user_id}:*"
"""

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status

from src.repository.transaction_repository import TransactionRepository
from src.shared.services.redis_service import RedisService
from src.shared.utils.logger import logger
from .dtos import CreateTransactionDTO, UpdateTransactionDTO, TransactionResponse
from src.schemas.transactions import TransactionType
from src.schemas.categories import CategorySchema


CACHE_TTL = 10  # segundos


def _cache_key(user_id: int, month: int | None, year: int | None) -> str:
    return f"transactions:uid:{user_id}:m:{month}:y:{year}"


def _invalidate_user_cache(cache: RedisService, user_id: int) -> None:
    cache.delete_pattern(f"transactions:uid:{user_id}:*")


class TransactionsService:
    def __init__(
        self,
        repository: TransactionRepository,
        cache: RedisService,
    ):
        self.repository = repository
        self.cache = cache

    def find_all(self, user_id: int, month: int | None = None, year: int | None = None) -> list:
        key = _cache_key(user_id, month, year)
        cached = self.cache.get(key)

        if cached:
            logger.info(f"Cache HIT → {key}")
            raw = json.loads(cached)
            return raw

        logger.info(f"Cache MISS → {key} — buscando no banco")
        results = self.repository.find_all_by_user(user_id, month=month, year=year)

        try:
            from fastapi.encoders import jsonable_encoder
            
            # Converte e garante o relationship manual para formato RAW
            raw_results = []
            for t in results:
                t_dict = {c.name: getattr(t, c.name) for c in t.__table__.columns}
                t_dict['category'] = (
                    {c.name: getattr(t.category, c.name) for c in t.category.__table__.columns}
                ) if t.category else None
                raw_results.append(t_dict)

            serialized = json.dumps(jsonable_encoder(raw_results))

            self.cache.set(key, serialized, ttl=CACHE_TTL)
        except Exception as e:
            logger.warning(f"Falha ao serializar para cache: {e}")

        return results

    def create(self, user_id: int, data: CreateTransactionDTO):
        if data.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O valor da transação deve ser positivo"
            )

        category_id = None
        if data.category_code:
            from sqlalchemy import select

            result = self.repository.session.execute(
                select(CategorySchema)
                .where(CategorySchema.code == data.category_code)
                .where(CategorySchema.user_id == user_id)
                .where(CategorySchema.deleted_at == None)  # noqa: E711
            ).scalar_one_or_none()
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Categoria não encontrada"
                )
            category_id = result.id
        try:
            record = self.repository.create({
                "title": data.title,
                "amount": data.amount,
                "type": TransactionType[data.type.value.upper()],
                "due_date": data.due_date,
                "description": data.description,
                "is_paid": data.is_paid,
                "paid_at": datetime.now(timezone.utc) if data.is_paid else None,
                "user_id": user_id,
                "category_id": category_id,
            })
            _invalidate_user_cache(self.cache, user_id)
            return record
        except Exception as e:
            logger.error(f"Erro ao criar transação: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar transação"
            )

    def mark_as_paid(self, user_id: int, transaction_code: UUID):
        transaction = self.repository.find_by_code(transaction_code, user_id)
        if not transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transação não encontrada")

        transaction.is_paid = not transaction.is_paid
        transaction.paid_at = datetime.now(timezone.utc) if transaction.is_paid else None
        result = self.repository.update(transaction)
        _invalidate_user_cache(self.cache, user_id)
        return result

    def update(
        self,
        user_id: int,
        transaction_code: UUID,
        data: UpdateTransactionDTO,
        category: CategorySchema | None
    ):
        transaction = self.repository.find_by_code(transaction_code, user_id)

        if not transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transação não encontrada")

        if data.title is not None:
            transaction.title = data.title

        if data.amount is not None:
            if data.amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="O valor da transação deve ser positivo"
                )
            transaction.amount = data.amount

        if data.type is not None:
            transaction.type = TransactionType[data.type.value.upper()]

        if data.due_date is not None:
            transaction.due_date = data.due_date

        if data.description is not None:
            transaction.description = data.description

        if data.is_paid is not None:
            transaction.is_paid = data.is_paid
            transaction.paid_at = datetime.now(timezone.utc) if data.is_paid else None

        if category is not None:
            transaction.category_id = category.id

        result = self.repository.update(transaction)
        _invalidate_user_cache(self.cache, user_id)
        return result

    def remove(self, user_id: int, transaction_code: UUID):
        transaction = self.repository.find_by_code(transaction_code, user_id)
        if not transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transação não encontrada")

        self.repository.soft_delete(transaction)
        _invalidate_user_cache(self.cache, user_id)
