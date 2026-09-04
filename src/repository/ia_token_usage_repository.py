from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.schemas.accounts import AccountSchema
from src.schemas.ia_token_usage import IaOperation, IaTokenUsageSchema


class IaTokenUsageRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def create(
        self,
        account_id: int,
        user_id: int | None,
        operation: IaOperation,
        model: str,
        tokens_input: int,
        tokens_output: int,
    ) -> IaTokenUsageSchema:
        record = IaTokenUsageSchema(
            account_id=account_id,
            user_id=user_id,
            operation=operation,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_aggregated(
        self,
        account_code: UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Retorna consumo agregado por conta."""
        query = (
            select(
                AccountSchema.code.label("account_code"),
                AccountSchema.name.label("account_name"),
                func.sum(IaTokenUsageSchema.tokens_input).label("total_input"),
                func.sum(IaTokenUsageSchema.tokens_output).label("total_output"),
                func.count(IaTokenUsageSchema.id).label("call_count"),
            )
            .join(AccountSchema, AccountSchema.id == IaTokenUsageSchema.account_id)
            .group_by(AccountSchema.code, AccountSchema.name)
        )

        if account_code:
            query = query.where(AccountSchema.code == account_code)
        if start_date:
            query = query.where(IaTokenUsageSchema.created_at >= start_date)
        if end_date:
            query = query.where(IaTokenUsageSchema.created_at <= end_date)

        rows = self.session.execute(query).all()
        return [
            {
                "account_code": str(row.account_code),
                "account_name": row.account_name,
                "total_input": row.total_input or 0,
                "total_output": row.total_output or 0,
                "call_count": row.call_count or 0,
            }
            for row in rows
        ]

    def list_by_account(
        self, account_id: int, page: int, page_size: int
    ) -> tuple[list[IaTokenUsageSchema], int]:
        """Retorna log paginado de chamadas de uma conta."""
        base_query = select(IaTokenUsageSchema).where(
            IaTokenUsageSchema.account_id == account_id
        )
        total = self.session.execute(
            select(func.count()).select_from(base_query.subquery())
        ).scalar_one()
        items = self.session.execute(
            base_query.order_by(IaTokenUsageSchema.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        return list(items), total
