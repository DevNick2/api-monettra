from fastapi import HTTPException
from src.repository.analytics_repository import AnalyticsRepository
from src.shared.utils.logger import logger
from datetime import datetime, date
from uuid import UUID
from src.modules.analytics.ols_helper import OLSHelper
from .dtos import CategoryAnalyticsResponse, AccumulatedAnalyticsResponse, TrendAnalyticsResponse

class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    def get_expenses_by_category(self, account_id: int, start_date: date, end_date: date) -> list[CategoryAnalyticsResponse]:
        results = self.repository.get_expenses_by_category(account_id, start_date, end_date)
        return [
            CategoryAnalyticsResponse(
                category_name=row.category_name,
                category_color=row.category_color,
                total=row.total / 100.0 if row.total else 0.0
            ) for row in results
        ]

    def get_accumulated_expenses(self, account_id: int, start_date: date, end_date: date, group_by: str) -> list[AccumulatedAnalyticsResponse]:
        if group_by not in ["day", "week", "month"]:
            raise HTTPException(status_code=422, detail="group_by deve ser 'day', 'week' ou 'month'")

        results = self.repository.get_accumulated_expenses(account_id, start_date, end_date, group_by)

        if group_by == "month":
            MONTH_LABELS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            # Mapeia os meses retornados pelo banco (1-12) para seus totais
            totals_by_month: dict[int, float] = {}
            for row in results:
                month_num = int(row.period) if row.period else 0
                totals_by_month[month_num] = (row.total / 100.0) if row.total else 0.0

            # Garante os 12 meses, preenchendo com 0.0 os que não têm dados
            return [
                AccumulatedAnalyticsResponse(
                    label=MONTH_LABELS[m - 1],
                    total=totals_by_month.get(m, 0.0)
                )
                for m in range(1, 13)
            ]

        response = []
        accumulated = 0.0
        for row in results:
            period_val = int(row.period) if row.period else 0
            accumulated += (row.total / 100.0) if row.total else 0.0

            label = f"Dia {period_val}" if group_by == "day" else f"Semana {period_val}"
            response.append(AccumulatedAnalyticsResponse(
                label=label,
                total=accumulated
            ))

        return response

    def get_trend_by_category(
        self, account_id: int, year: int, category_codes: list[str] | None = None
    ) -> list[TrendAnalyticsResponse]:
        # Resolve category_codes if they are given as strings, the repository compares UUIDs
        codes = [UUID(c) for c in category_codes] if category_codes else None

        results = self.repository.get_trend_by_category(account_id, year, codes)

        today = date.today()
        if year < today.year:
            observed_months = 12
        elif year > today.year:
            observed_months = 0
        else:
            observed_months = today.month

        category_map = {}
        for row in results:
            cat_code = str(row.category_code)
            if cat_code not in category_map:
                category_map[cat_code] = {
                    "name": row.category_name,
                    "color": row.category_color,
                    "months": [0.0] * 12
                }
            m_idx = int(row.month) - 1 # 0 index
            category_map[cat_code]["months"][m_idx] += row.total / 100.0 if row.total else 0.0

        response = []
        for code, data in category_map.items():
            months_data = data["months"]
            
            x_vals = []
            y_vals = []
            for i in range(observed_months):
                x_vals.append(float(i + 1))
                y_vals.append(months_data[i])
                
            m, b, r2 = OLSHelper.calculate_linear_regression(x_vals, y_vals)
            
            history = list(months_data)
            # Projetar os meses não observados
            for i in range(observed_months, 12):
                predicted = m * (i + 1) + b
                history[i] = max(0.0, predicted) # evitar valores negativos

            projected_total = sum(history)
            
            response.append(TrendAnalyticsResponse(
                category_code=code,
                category_name=data["name"],
                category_color=data["color"],
                history=history,
                m=m,
                b=b,
                r2=r2,
                projected_total=projected_total
            ))
            
        return response
