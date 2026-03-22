"""
TransactionsService — Regras de negócio do módulo de transações.

Cache Redis:
  - find_all  → cacheado por 60s. Chave: "transactions:uid:{user_id}:m:{month}:y:{year}"
  - Qualquer operação de escrita (create, update, remove, mark_as_paid)
    invalida todas as chaves do usuário via padrão "transactions:uid:{user_id}:*"
"""

import json
import re
import io
import uuid
import calendar

from datetime import datetime, timezone, date
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from src.repository.transaction_repository import TransactionRepository
from src.shared.services.redis_service import RedisService
from src.shared.utils.logger import logger
from .dtos import (
    CreateTransactionDTO,
    BatchCreateTransactionDTO,
    UpdateTransactionDTO,
    TransactionResponse,
)
from src.schemas.transactions import TransactionType
from src.schemas.categories import CategorySchema
from ofxtools.Parser import OFXTree, TreeBuilder
import xml.etree.ElementTree as ET
import logging

logging.getLogger('ofxtools').setLevel(logging.WARNING)


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
        key = f"{RedisService.TRANSACTIONS_CACHE_PREFIX}:{user_id}:m:{month}:y:{year}"
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

        category_id = self._resolve_category(user_id, data.category_code)

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
            
            self.cache.delete_pattern(f"{RedisService.TRANSACTIONS_CACHE_PREFIX}:{user_id}:*")
            return record
        except Exception as e:
            logger.error(f"Erro ao criar transação: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar transação"
            )

    def create_batch(self, user_id: int, data: BatchCreateTransactionDTO) -> list:
        """
        Cria um grupo de transações recorrentes partindo da start_date até Dezembro do mesmo ano.
        Todas as parcelas compartilham o mesmo recurrence_id.
        """
        if data.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O valor da transação deve ser positivo"
            )

        category_id = self._resolve_category(user_id, data.category_code)
        recurrence_id = uuid.uuid4()

        start = data.start_date
        records = []
        for month in range(start.month, 13):
            last_day = calendar.monthrange(start.year, month)[1]
            day = min(start.day, last_day)
            records.append({
                "title": data.title,
                "amount": data.amount,
                "type": TransactionType[data.type.value.upper()],
                "due_date": date(start.year, month, day),
                "description": data.description,
                "is_paid": data.is_paid,
                "paid_at": datetime.now(timezone.utc) if data.is_paid else None,
                "user_id": user_id,
                "category_id": category_id,
                "recurrence_id": recurrence_id,
            })

        try:
            result = self.repository.bulk_create(records)
            _invalidate_user_cache(self.cache, user_id)
            return result
        except Exception as e:
            logger.error(f"Erro ao criar transações em lote: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar lote de transações"
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

        scope = data.scope  # "single" | "forward" | "all"

        # Determina quais transações serão afetadas
        targets = [transaction]
        if scope != "single" and transaction.recurrence_id:
            if scope == "forward":
                targets = self.repository.find_by_recurrence_forward(
                    transaction.recurrence_id, user_id, transaction.due_date
                )
            elif scope == "all":
                targets = self.repository.find_all_by_recurrence(
                    transaction.recurrence_id, user_id
                )

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
            if data.is_paid is not None:
                t.is_paid = data.is_paid
                t.paid_at = datetime.now(timezone.utc) if data.is_paid else None
            # A data só muda para o registro "single" para preservar as datas cronológicas dos irmãos
            if data.due_date is not None and scope == "single":
                t.due_date = data.due_date
            # Categoria é propagada em todos os escopos
            if category is not None:
                t.category_id = category.id

        # Persiste apenas o primeiro (ou todos via ORM dirty tracking)
        self.repository.update(targets[0])
        if len(targets) > 1:
            self.repository.session.commit()

        _invalidate_user_cache(self.cache, user_id)
        return targets[0]

    def remove(self, user_id: int, transaction_code: UUID, scope: str = "single"):
        transaction = self.repository.find_by_code(transaction_code, user_id)
        if not transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transação não encontrada")

        if scope == "single" or not transaction.recurrence_id:
            self.repository.soft_delete(transaction)
        elif scope == "forward":
            targets = self.repository.find_by_recurrence_forward(
                transaction.recurrence_id, user_id, transaction.due_date
            )
            self.repository.bulk_soft_delete(targets)
        elif scope == "all":
            targets = self.repository.find_all_by_recurrence(
                transaction.recurrence_id, user_id
            )
            self.repository.bulk_soft_delete(targets)

        _invalidate_user_cache(self.cache, user_id)

    def _resolve_category(self, user_id: int, category_code) -> int | None:
        """Resolve o category_code para o ID interno, ou None."""
        if not category_code:
            return None
        from sqlalchemy import select
        result = self.repository.session.execute(
            select(CategorySchema)
            .where(CategorySchema.code == category_code)
            .where(CategorySchema.user_id == user_id)
            .where(CategorySchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada"
            )
        return result.id

    async def import_ofx(self, user_id: int, file: UploadFile):
        parser = await self.sanitize_ofx_content(file)

        try:
            ofx = parser.convert()

            for statement in ofx.statements:
                for tx in statement.banktranlist:
                    descricao = (tx.name or tx.memo or "Transação sem nome").strip()
                    print(f"Data: {tx.dtposted} | Valor: {tx.trnamt} | Descrição: {descricao}")

        except Exception as e:
            print(f"Erro ao processar OFX para o usuário {user_id}: {e}")
            return False

        return True

    async def sanitize_ofx_content(self, file: UploadFile) -> OFXTree:
        raw_bytes = await file.read()

        parser = OFXTree()
        parser.parse(io.BytesIO(raw_bytes))

        root = parser.getroot()

        for transaction in root.iter('STMTTRN'):
            name = transaction.find('NAME')
            memo = transaction.find('MEMO')
            if name is None:
                print('Name missing')
                continue
            if memo is None:
                continue

            old_name_text = name.text
            name.text = memo.text

            if old_name_text:
                memo.text = old_name_text

                children = list(transaction)
                name_idx = children.index(name)
                memo_idx = children.index(memo)

                if name_idx > memo_idx:
                    transaction.remove(name)
                    transaction.insert(memo_idx, name)
            else:
                transaction.remove(memo)

        return parser
