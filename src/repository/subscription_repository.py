from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.schemas.subscriptions import SubscriptionSchema


class SubscriptionRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession()

    def find_all_by_user(self, user_id: int) -> list[SubscriptionSchema]:
        query = (
            select(SubscriptionSchema)
            .where(SubscriptionSchema.user_id == user_id)
            .where(SubscriptionSchema.deleted_at == None)  # noqa: E711
            .order_by(SubscriptionSchema.created_at.desc())
        )
        return self.session.execute(query).scalars().all()

    def find_active_by_user(self, user_id: int) -> list[SubscriptionSchema]:
        query = (
            select(SubscriptionSchema)
            .where(SubscriptionSchema.user_id == user_id)
            .where(SubscriptionSchema.is_active == True)  # noqa: E712
            .where(SubscriptionSchema.deleted_at == None)  # noqa: E711
            .order_by(SubscriptionSchema.created_at.desc())
        )
        return self.session.execute(query).scalars().all()

    def find_by_code(self, code: UUID, user_id: int) -> SubscriptionSchema | None:
        return self.session.execute(
            select(SubscriptionSchema)
            .where(SubscriptionSchema.code == code)
            .where(SubscriptionSchema.user_id == user_id)
            .where(SubscriptionSchema.deleted_at == None)  # noqa: E711
        ).scalars().first()

    def create(self, data: dict) -> SubscriptionSchema:
        subscription = SubscriptionSchema(**data)
        self.session.add(subscription)
        self.session.commit()
        self.session.refresh(subscription)
        return subscription

    def update(self, subscription: SubscriptionSchema) -> SubscriptionSchema:
        self.session.commit()
        self.session.refresh(subscription)
        return subscription

    def soft_delete(self, subscription: SubscriptionSchema) -> None:
        subscription.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
