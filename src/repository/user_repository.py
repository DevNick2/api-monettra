from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone

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