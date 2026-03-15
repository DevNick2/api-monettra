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
        query = (
            select(TransactionSchema)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
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

    def update(self, transaction: TransactionSchema) -> TransactionSchema:
        self.session.commit()
        self.session.refresh(transaction)
        return transaction

    def soft_delete(self, transaction: TransactionSchema) -> None:
        transaction.deleted_at = datetime.now(timezone.utc)
        self.session.commit()

    def horizon(self, user_id: int) -> list:
        query = (
            select(TransactionSchema)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
        )

        return self.session.execute(query).scalars().all()
