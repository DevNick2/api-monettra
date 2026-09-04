from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.schemas.accounts import AccountMemberSchema
from src.schemas.users import UserSchema


class UserRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def find_all(self):
        return self.session.execute(
            select(UserSchema).where(UserSchema.deleted_at == None)  # noqa: E711
        ).scalars().all()

    def find_by_email(self, email: str) -> UserSchema | None:
        return self.session.execute(
            select(UserSchema).where(UserSchema.email == email)
        ).scalar_one_or_none()

    def find_by_code(self, code: UUID | str) -> UserSchema | None:
        return self.session.execute(
            select(UserSchema).where(
                UserSchema.code == code,
                UserSchema.deleted_at == None,  # noqa: E711
            )
        ).scalar_one_or_none()

    def find_paginated(self, page: int, page_size: int) -> tuple[list[UserSchema], int]:
        """Retorna (items, total) com paginação, excluindo soft-deleted."""
        base_query = select(UserSchema).where(UserSchema.deleted_at == None)  # noqa: E711
        total = self.session.execute(
            select(func.count()).select_from(base_query.subquery())
        ).scalar_one()
        items = self.session.execute(
            base_query
            .order_by(UserSchema.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        return list(items), total

    def create(self, data: dict) -> UserSchema:
        user = UserSchema(**data)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(self, user: UserSchema, data: dict) -> UserSchema:
        for field, value in data.items():
            if value is not None:
                setattr(user, field, value)
        self.session.commit()
        self.session.refresh(user)
        return user

    def deactivate(self, user: UserSchema) -> UserSchema:
        user.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(user)
        return user

    def hard_delete(self, user: UserSchema) -> None:
        """Hard delete: remove o usuário e membros de conta em cascata."""
        self.session.execute(
            AccountMemberSchema.__table__.delete().where(
                AccountMemberSchema.user_id == user.id
            )
        )
        self.session.delete(user)
        self.session.commit()