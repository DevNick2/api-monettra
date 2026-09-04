from datetime import datetime, timezone, date
from uuid import UUID

from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import select, extract, func, case

from src.schemas.transactions import TransactionSchema, TransactionType, TransactionClassification
from src.schemas.categories import CategorySchema

class TransactionRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession

    def find_all_by_account(
        self,
        account_id: int,
        month: int | None = None,
        year: int | None = None
    ) -> list[TransactionSchema]:
        from src.schemas.subscriptions import SubscriptionSchema
        
        query = (
            select(TransactionSchema)
            .outerjoin(SubscriptionSchema, TransactionSchema.subscription_id == SubscriptionSchema.id)
            .where(TransactionSchema.account_id == account_id)
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

    def find_by_code(self, code: UUID, account_id: int) -> TransactionSchema | None:
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.code == code)
            .where(TransactionSchema.account_id == account_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
        ).scalars().first()

    def find_by_code_ignore_account(self, code: UUID) -> TransactionSchema | None:
        """
        Busca uma transação pelo code sem filtrar por account_id.
        Usado quando a checagem de account isolation precisa distinguir
        entre "não encontrada" (404) e "pertence a outra conta" (403).
        """
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.code == code)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
        ).scalars().first()

    def find_default_by_month(
        self,
        account_id: int,
        month: int,
        year: int,
    ) -> list[TransactionSchema]:
        """
        Retorna as transações elegíveis para duplicação de mês:
        type_of_transaction = DEFAULT, sem subscription_id/invoice_id,
        no mês/ano informado, dentro da conta ativa.
        """
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.account_id == account_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .where(TransactionSchema.type_of_transaction == TransactionClassification.DEFAULT)
            .where(TransactionSchema.subscription_id == None)  # noqa: E711
            .where(TransactionSchema.invoice_id == None)  # noqa: E711
            .where(extract("month", TransactionSchema.due_date) == month)
            .where(extract("year", TransactionSchema.due_date) == year)
        ).scalars().all()

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
        account_id: int,
        from_date: date
    ) -> list[TransactionSchema]:
        """Retorna todas as parcelas de uma recorrência iguais ou posteriores à data informada."""
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.recurrence_id == recurrence_id)
            .where(TransactionSchema.account_id == account_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .where(TransactionSchema.due_date >= from_date)
            .order_by(TransactionSchema.due_date)
        ).scalars().all()

    def find_all_by_recurrence(
        self,
        recurrence_id: UUID,
        account_id: int
    ) -> list[TransactionSchema]:
        """Retorna TODAS as parcelas de uma recorrência (passadas e futuras)."""
        return self.session.execute(
            select(TransactionSchema)
            .where(TransactionSchema.recurrence_id == recurrence_id)
            .where(TransactionSchema.account_id == account_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .order_by(TransactionSchema.due_date)
        ).scalars().all()

    def bulk_soft_delete(self, transactions: list[TransactionSchema]) -> None:
        """Aplica soft delete em várias transações de uma vez."""
        now = datetime.now(timezone.utc)
        for t in transactions:
            t.deleted_at = now
        self.session.commit()

    def horizon(self, account_id: int) -> list:
        query = (
            select(TransactionSchema)
            .where(TransactionSchema.account_id == account_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
        )

        return self.session.execute(query).scalars().all()

    def get_summary_by_account(
        self,
        account_id: int,
        month: int | None = None,
        year: int | None = None,
    ) -> dict:
        """
        Agrega receitas e despesas do período usando a mesma base de filtros
        de find_all_by_account (conta, mês/ano, soft delete, assinatura ativa).
        Retorna totais gerais e totais de transações pagas (is_paid=True).
        Todos os valores em centavos (int).
        """
        from src.schemas.subscriptions import SubscriptionSchema

        income_expr = case(
            (TransactionSchema.type == TransactionType.INCOME, TransactionSchema.amount),
            else_=0,
        )
        expense_expr = case(
            (TransactionSchema.type == TransactionType.EXPENSE, TransactionSchema.amount),
            else_=0,
        )
        paid_income_expr = case(
            (
                (TransactionSchema.type == TransactionType.INCOME) & (TransactionSchema.is_paid == True),  # noqa: E712
                TransactionSchema.amount,
            ),
            else_=0,
        )
        paid_expense_expr = case(
            (
                (TransactionSchema.type == TransactionType.EXPENSE) & (TransactionSchema.is_paid == True),  # noqa: E712
                TransactionSchema.amount,
            ),
            else_=0,
        )

        query = (
            select(
                func.coalesce(func.sum(income_expr), 0).label("total_income"),
                func.coalesce(func.sum(expense_expr), 0).label("total_expense"),
                func.coalesce(func.sum(paid_income_expr), 0).label("paid_income"),
                func.coalesce(func.sum(paid_expense_expr), 0).label("paid_expense"),
            )
            .outerjoin(SubscriptionSchema, TransactionSchema.subscription_id == SubscriptionSchema.id)
            .where(TransactionSchema.account_id == account_id)
            .where(TransactionSchema.deleted_at == None)  # noqa: E711
            .where(
                (TransactionSchema.subscription_id == None)  # noqa: E711
                | (SubscriptionSchema.is_active == True)  # noqa: E712
            )
        )

        if month is not None:
            query = query.where(extract("month", TransactionSchema.due_date) == month)
        if year is not None:
            query = query.where(extract("year", TransactionSchema.due_date) == year)

        row = self.session.execute(query).one()
        total_income = int(row.total_income)
        total_expense = int(row.total_expense)
        paid_income = int(row.paid_income)
        paid_expense = int(row.paid_expense)

        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "net_balance": total_income - total_expense,
            "paid_income": paid_income,
            "paid_expense": paid_expense,
            "paid_net_balance": paid_income - paid_expense,
        }
