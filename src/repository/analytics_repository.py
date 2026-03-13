from sqlalchemy.orm import Session
from sqlalchemy import select, func, extract
from src.schemas.transactions import TransactionSchema, TransactionType
from src.schemas.categories import CategorySchema
from typing import Literal
from datetime import date

class AnalyticsRepository:
    def __init__(self, db_session: Session):
        self.session = db_session()

    def get_expenses_by_category(self, user_id: int, start_date: date, end_date: date):
        query = (
            select(
                CategorySchema.title.label("category_name"),
                CategorySchema.color.label("category_color"),
                func.sum(TransactionSchema.amount).label("total")
            )
            .join(TransactionSchema.category)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)
            .where(TransactionSchema.type == TransactionType.EXPENSE)
            .where(TransactionSchema.due_date >= start_date)
            .where(TransactionSchema.due_date <= end_date)
            .group_by(CategorySchema.title, CategorySchema.color)
        )
        return self.session.execute(query).all()

    def get_accumulated_expenses(self, user_id: int, start_date: date, end_date: date, group_by: str):
        # group_by: "day" or "week"
        group_expr = extract("day", TransactionSchema.due_date) if group_by == "day" else extract("week", TransactionSchema.due_date)
        
        query = (
            select(
                group_expr.label("period"),
                func.sum(TransactionSchema.amount).label("total")
            )
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)
            .where(TransactionSchema.type == TransactionType.EXPENSE)
            .where(TransactionSchema.due_date >= start_date)
            .where(TransactionSchema.due_date <= end_date)
            .group_by(group_expr)
            .order_by(group_expr)
        )
        return self.session.execute(query).all()

    def get_trend_by_category(self, user_id: int, month: int, year: int, previous_month: int, previous_year: int, category_codes: list[str] = None):
        # We need to query expenses for current month and previous month for the given categories
        
        base_query = (
            select(
                CategorySchema.code.label("category_code"),
                CategorySchema.title.label("category_name"),
                CategorySchema.color.label("category_color"),
                func.sum(TransactionSchema.amount).label("total")
            )
            .join(TransactionSchema.category)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)
            .where(TransactionSchema.type == TransactionType.EXPENSE)
        )

        if category_codes:
            base_query = base_query.where(CategorySchema.code.in_(category_codes))

        current_query = (
            base_query
            .where(extract("month", TransactionSchema.due_date) == month)
            .where(extract("year", TransactionSchema.due_date) == year)
            .group_by(CategorySchema.code, CategorySchema.title, CategorySchema.color)
        )

        previous_query = (
            base_query
            .where(extract("month", TransactionSchema.due_date) == previous_month)
            .where(extract("year", TransactionSchema.due_date) == previous_year)
            .group_by(CategorySchema.code, CategorySchema.title, CategorySchema.color)
        )

        current_results = self.session.execute(current_query).all()
        previous_results = self.session.execute(previous_query).all()

        return current_results, previous_results
