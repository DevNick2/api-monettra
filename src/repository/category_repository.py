from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.schemas.categories import CategorySchema


class CategoryRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession()

    def find_all_by_user(self, user_id: int) -> list[CategorySchema]:
        return self.session.execute(
            select(CategorySchema)
            .where(CategorySchema.user_id == user_id)
            .where(CategorySchema.deleted_at == None)  # noqa: E711
        ).scalars().all()

    def find_by_code(self, code: UUID) -> CategorySchema | None:
        return self.session.execute(
            select(CategorySchema)
            .where(CategorySchema.code == code)
            .where(CategorySchema.deleted_at == None)  # noqa: E711
        ).scalar_one_or_none()

    def create(self, data: dict) -> CategorySchema:
        category = CategorySchema(**data)
        self.session.add(category)
        self.session.commit()
        self.session.refresh(category)
        return category

    def update(self, category: CategorySchema) -> CategorySchema:
        self.session.commit()
        self.session.refresh(category)
        return category

    def soft_delete(self, category: CategorySchema) -> None:
        category.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
