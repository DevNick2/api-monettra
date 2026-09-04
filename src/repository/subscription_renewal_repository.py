from sqlalchemy import select
from sqlalchemy.orm import Session

from src.schemas.subscription_renewals import SubscriptionRenewalSchema


class SubscriptionRenewalRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def create(self, data: dict) -> SubscriptionRenewalSchema:
        renewal = SubscriptionRenewalSchema(**data)
        self.session.add(renewal)
        self.session.commit()
        self.session.refresh(renewal)
        return renewal

    def find_all_by_subscription(self, subscription_id: int) -> list[SubscriptionRenewalSchema]:
        query = (
            select(SubscriptionRenewalSchema)
            .where(SubscriptionRenewalSchema.subscription_id == subscription_id)
            .order_by(SubscriptionRenewalSchema.renewed_at.desc())
        )
        return self.session.execute(query).scalars().all()
