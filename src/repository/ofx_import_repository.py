"""
OfxImportRepository — Acesso ao banco para rastreamento de importações OFX.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.schemas.ofx_imports import OfxImportSchema


class OfxImportRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def create(self, data: dict) -> OfxImportSchema:
        record = OfxImportSchema(**data)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def find_by_code(self, code, account_id: int) -> OfxImportSchema | None:
        return self.session.execute(
            select(OfxImportSchema)
            .where(OfxImportSchema.code == code)
            .where(OfxImportSchema.account_id == account_id)
        ).scalar_one_or_none()

    def find_latest_by_account(self, account_id: int) -> OfxImportSchema | None:
        return self.session.execute(
            select(OfxImportSchema)
            .where(OfxImportSchema.account_id == account_id)
            .order_by(OfxImportSchema.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def find_all_by_account(self, account_id: int) -> list[OfxImportSchema]:
        return self.session.execute(
            select(OfxImportSchema)
            .where(OfxImportSchema.account_id == account_id)
            .order_by(OfxImportSchema.created_at.desc())
        ).scalars().all()

    def find_active_by_account(self, account_id: int) -> OfxImportSchema | None:
        """Retorna importação em progresso (pending/processing) para a conta."""
        return self.session.execute(
            select(OfxImportSchema)
            .where(OfxImportSchema.account_id == account_id)
            .where(OfxImportSchema.status.in_(["pending", "processing"]))
            .order_by(OfxImportSchema.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def update(self, record: OfxImportSchema) -> OfxImportSchema:
        self.session.commit()
        self.session.refresh(record)
        return record

