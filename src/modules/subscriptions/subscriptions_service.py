"""
SubscriptionsService — Regras de negócio do módulo de assinaturas.

Regras de estado:
  - is_active controlado manualmente via toggle (Regra Suprema).
  - Se billing_date < hoje → serviço já venceu (lógica de exibição no frontend).
  - Se is_active=False, assinatura não entra nos cálculos de analytics.
"""

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status

from src.repository.subscription_repository import SubscriptionRepository
from src.schemas.subscriptions import RecurrenceType as SchemaRecurrenceType
from src.shared.utils.logger import logger
from .dtos import CreateSubscriptionDTO, UpdateSubscriptionDTO
from src.shared.services.redis_service import RedisService


class SubscriptionsService:
    def __init__(
        self,
        repository: SubscriptionRepository,
        cache: RedisService,
        transaction_repository=None,
    ):
        self.repository = repository
        self.transaction_repository = transaction_repository
        self.cache = cache

    def find_all(self, user_id: int) -> list:
        return self.repository.find_all_by_user(user_id)

    def find_active(self, user_id: int) -> list:
        return self.repository.find_active_by_user(user_id)

    def create(self, user_id: int, data: CreateSubscriptionDTO):
        if data.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O valor da assinatura deve ser positivo",
            )

        try:
            record = self.repository.create({
                "provider": data.provider,
                "recurrence": SchemaRecurrenceType[data.recurrence.value.upper()],
                "billing_date": data.billing_date,
                "has_trial": data.has_trial,
                "is_active": data.is_active,
                "description": data.description,
                "user_id": user_id,
            })
            
            # XXX TODO :: Refatorar, por que não usar o transactions_service.create ou bulk_create?
            if self.transaction_repository:
                import uuid
                import calendar
                from src.schemas.transactions import TransactionType, TransactionClassification

                recurrence_id = uuid.uuid4()
                start = data.billing_date or date.today()
                
                records = []
                for month in range(start.month, 13):
                    last_day = calendar.monthrange(start.year, month)[1]
                    day = min(start.day, last_day)
                    
                    records.append({
                        "title": data.provider,
                        "amount": data.amount,
                        "type": TransactionType.EXPENSE,
                        "due_date": date(start.year, month, day),
                        "description": data.description or "Lançamento automático de assinatura",
                        "type_of_transaction": TransactionClassification.SUBSCRIPTION,
                        "is_paid": False,
                        "paid_at": None,
                        "user_id": user_id,
                        "category_id": None,
                        "subscription_id": record.id,
                        "recurrence_id": recurrence_id,
                    })                
                self.transaction_repository.bulk_create(records)
                self.cache.delete_pattern(f"{RedisService.TRANSACTIONS_CACHE_PREFIX}:{user_id}:*")

            return record
        except Exception as e:
            logger.error(f"Erro ao criar assinatura: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar assinatura",
            )

    def toggle_active(self, user_id: int, subscription_code: UUID):
        """
        Regra Suprema: o toggle manual sempre sobrepõe qualquer inferência por data.
        """
        subscription = self.repository.find_by_code(subscription_code, user_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )

        subscription.is_active = not subscription.is_active

        self.cache.delete_pattern(f"{RedisService.TRANSACTIONS_CACHE_PREFIX}:{user_id}:*")
        return self.repository.update(subscription)

    def update(self, user_id: int, subscription_code: UUID, data: UpdateSubscriptionDTO):
        subscription = self.repository.find_by_code(subscription_code, user_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )

        if data.provider is not None:
            subscription.provider = data.provider
        if data.amount is not None:
            if data.amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="O valor da assinatura deve ser positivo",
                )
            subscription.amount = data.amount
        if data.recurrence is not None:
            subscription.recurrence = SchemaRecurrenceType[data.recurrence.value.upper()]
        if data.billing_date is not None:
            subscription.billing_date = data.billing_date
        if data.has_trial is not None:
            subscription.has_trial = data.has_trial
        if data.is_active is not None:
            subscription.is_active = data.is_active
        if data.description is not None:
            subscription.description = data.description

        self.cache.delete_pattern(f"{RedisService.TRANSACTIONS_CACHE_PREFIX}:{user_id}:*")

        return self.repository.update(subscription)

    def remove(self, user_id: int, subscription_code: UUID):
        subscription = self.repository.find_by_code(subscription_code, user_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )

        self.repository.soft_delete(subscription)

        if self.transaction_repository:
            from src.schemas.transactions import TransactionSchema
            from sqlalchemy import select
            
            transactions_to_delete = self.transaction_repository.session.execute(
                select(TransactionSchema).where(
                    TransactionSchema.subscription_id == subscription.id,
                    TransactionSchema.deleted_at == None
                )
            ).scalars().all()
            
            if transactions_to_delete:
                self.transaction_repository.bulk_soft_delete(transactions_to_delete)
            
            self.cache.delete_pattern(f"{RedisService.TRANSACTIONS_CACHE_PREFIX}:{user_id}:*")
