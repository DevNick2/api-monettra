"""
SubscriptionsService — Regras de negócio do módulo de assinaturas.

Regras de estado:
  - is_active controlado manualmente via toggle (Regra Suprema).
  - Se billing_date < hoje → serviço já venceu (lógica de exibição no frontend).
  - Se is_active=False, assinatura não entra nos cálculos de analytics.
"""

import calendar
import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import select

from src.repository.subscription_repository import SubscriptionRepository
from src.schemas.subscriptions import (
    RecurrenceType as SchemaRecurrenceType,
)
from src.schemas.subscriptions import (
    SubscriptionPaymentMethod as SchemaPaymentMethod,
)
from src.schemas.transactions import TransactionClassification, TransactionSchema, TransactionType
from src.shared.services.redis_service import RedisService
from src.shared.utils.logger import logger

from .dtos import CreateSubscriptionDTO, UpdateSubscriptionDTO


class SubscriptionsService:
    def __init__(
        self,
        repository: SubscriptionRepository,
        cache: RedisService,
        transaction_repository=None,
        renewal_repository=None,
    ):
        self.repository = repository
        self.transaction_repository = transaction_repository
        self.renewal_repository = renewal_repository
        self.cache = cache

    def find_all(self, account_id: int) -> list:
        return self.repository.find_all_by_account(account_id)

    def find_active(self, account_id: int) -> list:
        return self.repository.find_active_by_account(account_id)

    def create(self, user_id: int, account_id: int, data: CreateSubscriptionDTO):
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
                "payment_method": SchemaPaymentMethod[data.payment_method.value.upper()],
                "user_id": user_id,  # Legacy
                "account_id": account_id,
            })
            
            # XXX TODO :: Refatorar, por que não usar o transactions_service.create ou bulk_create?
            if self.transaction_repository:
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
                        "user_id": user_id, # Legacy
                        "created_by": user_id,
                        "account_id": account_id,
                        "category_id": None,
                        "subscription_id": record.id,
                        "recurrence_id": recurrence_id,
                    })                
                self.transaction_repository.bulk_create(records)
                self.cache.delete_pattern(f"transactions:aid:{account_id}:*")

            return record
        except Exception as e:
            logger.error(f"Erro ao criar assinatura: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar assinatura",
            )

    def toggle_active(self, account_id: int, subscription_code: UUID):
        """
        Regra Suprema: o toggle manual sempre sobrepõe qualquer inferência por data.
        """
        subscription = self.repository.find_by_code(subscription_code, account_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )

        subscription.is_active = not subscription.is_active

        self.cache.delete_pattern(f"transactions:aid:{account_id}:*")
        return self.repository.update(subscription)

    def update(self, account_id: int, subscription_code: UUID, data: UpdateSubscriptionDTO):
        subscription = self.repository.find_by_code(subscription_code, account_id)
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
            # amount é derivado das transações filha: atualiza todas as futuras não pagas
            # XXX TODO :: Por que temos operações de repositórios aqui?
            # Toda e qualquer operação de banco deve ser feito no repository não no service
            if self.transaction_repository:
                today = date.today()
                pending = self.transaction_repository.session.execute(
                    select(TransactionSchema).where(
                        TransactionSchema.subscription_id == subscription.id,
                        TransactionSchema.is_paid == False,  # noqa: E712
                        TransactionSchema.due_date >= today,
                        TransactionSchema.deleted_at == None,  # noqa: E711
                    )
                ).scalars().all()
                for tx in pending:
                    tx.amount = data.amount
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
        if data.payment_method is not None:
            subscription.payment_method = SchemaPaymentMethod[data.payment_method.value.upper()]

        self.cache.delete_pattern(f"transactions:aid:{account_id}:*")

        return self.repository.update(subscription)

    def renew(self, account_id: int, subscription_code: UUID, user_id: int):
        subscription = self.repository.find_by_code(subscription_code, account_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )

        if not subscription.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Apenas assinaturas ativas podem ser renovadas",
            )

        today = date.today()
        if subscription.billing_date is None or subscription.billing_date > today:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A assinatura ainda não está vencida",
            )

        previous_billing_date = subscription.billing_date
        days_overdue = (today - previous_billing_date).days

        delta = (
            relativedelta(months=1)
            if subscription.recurrence == SchemaRecurrenceType.MONTHLY
            else relativedelta(years=1)
        )
        next_date = previous_billing_date + delta
        while next_date <= today:
            next_date += delta
        new_billing_date = next_date

        if self.renewal_repository:
            self.renewal_repository.create({
                "subscription_id": subscription.id,
                "renewed_by_user_id": user_id,
                "renewed_at": datetime.now(timezone.utc),
                "previous_billing_date": previous_billing_date,
                "new_billing_date": new_billing_date,
                "days_overdue": days_overdue,
            })

        subscription.billing_date = new_billing_date

        # XXX TODO :: Por que temos operações de repositórios aqui?
        # Toda e qualquer operação de banco deve ser feito no repository não no service
        if self.transaction_repository:
            overdue_tx = self.transaction_repository.session.execute(
                select(TransactionSchema).where(
                    TransactionSchema.subscription_id == subscription.id,
                    TransactionSchema.due_date == previous_billing_date,
                    TransactionSchema.is_paid == False,  # noqa: E712
                    TransactionSchema.deleted_at == None,  # noqa: E711
                )
            ).scalars().first()

            if overdue_tx:
                overdue_tx.is_paid = True
                overdue_tx.paid_at = datetime.now(timezone.utc)

        self.repository.update(subscription)
        self._invalidate_account_cache(account_id)
        return subscription

    def _invalidate_account_cache(self, account_id: int) -> None:
        self.cache.delete_pattern(f"transactions:aid:{account_id}:*")

    def remove(self, account_id: int, subscription_code: UUID):
        subscription = self.repository.find_by_code(subscription_code, account_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )

        self.repository.soft_delete(subscription)

        # XXX TODO :: Por que temos operações de repositórios aqui?
        # Toda e qualquer operação de banco deve ser feito no repository não no service
        if self.transaction_repository:
            transactions_to_delete = self.transaction_repository.session.execute(
                select(TransactionSchema).where(
                    TransactionSchema.subscription_id == subscription.id,
                    TransactionSchema.deleted_at == None  # noqa: E711
                )
            ).scalars().all()
            
            if transactions_to_delete:
                self.transaction_repository.bulk_soft_delete(transactions_to_delete)
            
            self.cache.delete_pattern(f"transactions:aid:{account_id}:*")
