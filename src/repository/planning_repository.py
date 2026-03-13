import calendar
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select, func

from sqlalchemy.orm import Session
from src.schemas.planning import PlanningEntrySchema
from src.schemas.transactions import TransactionType, TransactionSchema
from src.modules.planning.dtos import CreatePlanningEntryDTO, UpdatePlanningEntryDTO

def add_months(sourcedate: date, months: int) -> date:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

class PlanningRepository:
    def __init__(self, dbSession: Session):
        self.session = dbSession()

    def create_entry(self, user_id: int, dto: CreatePlanningEntryDTO, category_id: int | None) -> list[PlanningEntrySchema]:
        entries = []
        installments = dto.installments
        
        group_code = uuid.uuid4() if installments > 1 else None

        for i in range(installments):
            due_date = add_months(dto.due_date, i)
            entry = PlanningEntrySchema(
                title=dto.title,
                amount=dto.amount,
                type=TransactionType[dto.type.value.upper()],
                due_date=due_date,
                description=dto.description,
                installment_index=(i + 1) if installments > 1 else None,
                installment_total=installments if installments > 1 else None,
                group_code=group_code,
                user_id=user_id,
                category_id=category_id,
                is_materialized=False
            )
            entries.append(entry)

        self.session.add_all(entries)
        self.session.commit()
        for e in entries:
            self.session.refresh(e)
            
        return entries

    def find_all_by_user(self, user_id: int, start_date: date | None = None, end_date: date | None = None) -> list[PlanningEntrySchema]:
        query = (
            select(PlanningEntrySchema)
            .where(PlanningEntrySchema.user_id == user_id)
            .where(PlanningEntrySchema.deleted_at == None) # noqa: E711
        )
        if start_date:
            query = query.where(PlanningEntrySchema.due_date >= start_date)
        if end_date:
            query = query.where(PlanningEntrySchema.due_date <= end_date)
            
        query = query.order_by(PlanningEntrySchema.due_date.asc())
        return self.session.execute(query).scalars().all()

    def find_by_code(self, code: str, user_id: int) -> PlanningEntrySchema | None:
        return self.session.execute(
            select(PlanningEntrySchema)
            .where(PlanningEntrySchema.code == code)
            .where(PlanningEntrySchema.user_id == user_id)
            .where(PlanningEntrySchema.deleted_at == None) # noqa: E711
        ).scalars().first()

    def update_entry(self, user_id: int, dto: UpdatePlanningEntryDTO, entry: PlanningEntrySchema, category_id: int | None = None) -> list[PlanningEntrySchema]:
        if dto.scope == "this" or not entry.group_code:
            if dto.title is not None:
                entry.title = dto.title
            if dto.amount is not None:
                entry.amount = dto.amount
            if dto.type is not None:
                entry.type = dto.type
            if dto.due_date is not None:
                entry.due_date = dto.due_date
            if dto.description is not None:
                entry.description = dto.description
            if dto.category_code is not None:
                entry.category_id = category_id
            
            self.session.commit()
            self.session.refresh(entry)
            return [entry]
        else:
            query = (
                select(PlanningEntrySchema)
                .where(PlanningEntrySchema.group_code == entry.group_code)
                .where(PlanningEntrySchema.installment_index >= entry.installment_index)
                .where(PlanningEntrySchema.user_id == user_id)
                .where(PlanningEntrySchema.deleted_at == None)
                .order_by(PlanningEntrySchema.installment_index.asc())
            )
            future_entries = self.session.execute(query).scalars().all()
            
            base_date = dto.due_date
            
            for idx, fe in enumerate(future_entries):
                if dto.title is not None:
                    fe.title = dto.title
                if dto.amount is not None:
                    fe.amount = dto.amount
                if dto.type is not None:
                    fe.type = dto.type
                if dto.description is not None:
                    fe.description = dto.description
                if dto.category_code is not None:
                    fe.category_id = category_id
                if base_date is not None:
                    fe.due_date = add_months(base_date, idx)
            
            self.session.commit()
            return future_entries

    def delete_entry(self, user_id: int, entry: PlanningEntrySchema, scope: str) -> None:
        if scope == "this" or not entry.group_code:
            entry.deleted_at = datetime.now(timezone.utc)
        else:
            query = (
                select(PlanningEntrySchema)
                .where(PlanningEntrySchema.group_code == entry.group_code)
                .where(PlanningEntrySchema.installment_index >= entry.installment_index)
                .where(PlanningEntrySchema.user_id == user_id)
                .where(PlanningEntrySchema.deleted_at == None)
            )
            future_entries = self.session.execute(query).scalars().all()
            for fe in future_entries:
                fe.deleted_at = datetime.now(timezone.utc)
                
        self.session.commit()

    def materialize_entry(self, entry: PlanningEntrySchema, transaction_code: uuid.UUID) -> PlanningEntrySchema:
        entry.is_materialized = True
        entry.materialized_transaction_code = transaction_code
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def find_horizon(self, user_id: int, start_date: date, end_date: date):
        from src.schemas.transactions import TransactionSchema, TransactionType
        from src.schemas.categories import CategorySchema
        from sqlalchemy import text
        
        real_query = (
            select(
                func.to_char(TransactionSchema.due_date, 'YYYY-MM').label("year_month"),
                CategorySchema.code.label("category_code"),
                CategorySchema.title.label("category_title"),
                CategorySchema.color.label("category_color"),
                TransactionSchema.type,
                func.sum(TransactionSchema.amount).label("total")
            )
            .outerjoin(CategorySchema, TransactionSchema.category_id == CategorySchema.id)
            .where(TransactionSchema.user_id == user_id)
            .where(TransactionSchema.deleted_at == None)
            .where(TransactionSchema.due_date >= start_date)
            .where(TransactionSchema.due_date <= end_date)
            .group_by(text("year_month"), CategorySchema.code, CategorySchema.title, CategorySchema.color, TransactionSchema.type)
            .order_by(text("year_month"))
        )
        
        real_results = self.session.execute(real_query).all()
        
        planning_query = (
            select(
                func.to_char(PlanningEntrySchema.due_date, 'YYYY-MM').label("year_month"),
                CategorySchema.code.label("category_code"),
                CategorySchema.title.label("category_title"),
                CategorySchema.color.label("category_color"),
                PlanningEntrySchema.type,
                func.sum(PlanningEntrySchema.amount).label("total")
            )
            .outerjoin(CategorySchema, PlanningEntrySchema.category_id == CategorySchema.id)
            .where(PlanningEntrySchema.user_id == user_id)
            .where(PlanningEntrySchema.deleted_at == None)
            .where(PlanningEntrySchema.is_materialized == False)
            .where(PlanningEntrySchema.due_date >= start_date)
            .where(PlanningEntrySchema.due_date <= end_date)
            .group_by(text("year_month"), CategorySchema.code, CategorySchema.title, CategorySchema.color, PlanningEntrySchema.type)
            .order_by(text("year_month"))
        )
        
        planning_results = self.session.execute(planning_query).all()
        
        data_by_month = {}

        def get_cat_key(code, title, color):
            return (str(code) if code else "none", title or "Sem categoria", color)

        for ym, c_code, c_title, c_color, typ, tot in real_results:
            if ym not in data_by_month:
                data_by_month[ym] = {}
            cat_key = get_cat_key(c_code, c_title, c_color)
            if cat_key not in data_by_month[ym]:
                data_by_month[ym][cat_key] = {"real_income": 0, "real_expense": 0, "proj_income": 0, "proj_expense": 0}
            t_type = "income" if typ == TransactionType.INCOME else "expense"
            data_by_month[ym][cat_key][f"real_{t_type}"] += (tot or 0) / 100.0

        for ym, c_code, c_title, c_color, typ, tot in planning_results:
            if ym not in data_by_month:
                data_by_month[ym] = {}
            cat_key = get_cat_key(c_code, c_title, c_color)
            if cat_key not in data_by_month[ym]:
                data_by_month[ym][cat_key] = {"real_income": 0, "real_expense": 0, "proj_income": 0, "proj_expense": 0}
            t_type = "income" if typ == TransactionType.INCOME else "expense"
            data_by_month[ym][cat_key][f"proj_{t_type}"] += (tot or 0) / 100.0
            
        horizon_list = []
        for ym in sorted(data_by_month.keys()):
            cat_list = []
            month_net = 0
            for (c_code, c_title, c_color), vals in data_by_month[ym].items():
                r_inc = vals["real_income"]
                r_exp = vals["real_expense"]
                p_inc = vals["proj_income"]
                p_exp = vals["proj_expense"]
                net = (r_inc + p_inc) - (r_exp + p_exp)
                month_net += net
                cat_list.append({
                    "category_code": c_code if c_code != "none" else None,
                    "category_name": c_title,
                    "category_color": c_color,
                    "real_income": r_inc,
                    "real_expense": r_exp,
                    "projected_income": p_inc,
                    "projected_expense": p_exp
                })
                
            horizon_list.append({
                "year_month": ym,
                "categories": cat_list,
                "net_balance": month_net
            })
            
        return horizon_list
