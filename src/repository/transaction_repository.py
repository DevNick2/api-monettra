from datetime import datetime, timezone, date
from uuid import UUID

from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import select, extract, func

from src.schemas.transactions import TransactionSchema
from src.schemas.categories import CategorySchema

class TransactionRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession()

    def find_all_by_user(
        self,
        user_id: int,
        month: int | None = None,
        year: int | None = None
    ) -> list[TransactionSchema]:
        from src.schemas.subscriptions import SubscriptionSchema
        
        query = (
            select(TransactionSchema)
            .outerjoin(SubscriptionSchema, TransactionSchema.subscription_id == SubscriptionSchema.id)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .where(
                (TransactionSchema.subscription_id == None) | 
                (SubscriptionSchema.is_active == True)
            )
        )
        if month is not None:
            query = query.where(extract("month", TransactionSchema.due_date) == month)
        if year is not None:
            query = query.where(extract("year", TransactionSchema.due_date) == year)
        query = query.order_by(TransactionSchema.due_date.desc())
        return self.session.execute(query).scalars().all()

    def find_by_code(self, code: UUID, user_id: int) -> TransactionSchema | None:
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.code == code)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
        ).scalars().first()

    def create(self, data: dict) -> TransactionSchema:
        transaction = TransactionSchema(**data)
        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)
        return transaction

    def bulk_create(self, records: list[dict]) -> list[TransactionSchema]:
        """Cria múltiplas transações numa única transação de banco."""
        transactions = [TransactionSchema(**r) for r in records]
        self.session.add_all(transactions)
        self.session.commit()
        for t in transactions:
            self.session.refresh(t)
        return transactions

    def update(self, transaction: TransactionSchema) -> TransactionSchema:
        self.session.commit()
        self.session.refresh(transaction)
        return transaction

    def soft_delete(self, transaction: TransactionSchema) -> None:
        transaction.deleted_at = datetime.now(timezone.utc)
        self.session.commit()

    def find_by_recurrence_forward(
        self,
        recurrence_id: UUID,
        user_id: int,
        from_date: date
    ) -> list[TransactionSchema]:
        """Retorna todas as parcelas de uma recorrência iguais ou posteriores à data informada."""
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.recurrence_id == recurrence_id)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .where(TransactionSchema.due_date >= from_date)
            .order_by(TransactionSchema.due_date)
        ).scalars().all()

    def find_all_by_recurrence(
        self,
        recurrence_id: UUID,
        user_id: int
    ) -> list[TransactionSchema]:
        """Retorna TODAS as parcelas de uma recorrência (passadas e futuras)."""
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.recurrence_id == recurrence_id)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .order_by(TransactionSchema.due_date)
        ).scalars().all()

    def bulk_soft_delete(self, transactions: list[TransactionSchema]) -> None:
        """Aplica soft delete em várias transações de uma vez."""
        now = datetime.now(timezone.utc)
        for t in transactions:
            t.deleted_at = now
        self.session.commit()

    def horizon(self, user_id: int) -> list:
        query = (
            select(TransactionSchema)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
        )

        return self.session.execute(query).scalars().all()
