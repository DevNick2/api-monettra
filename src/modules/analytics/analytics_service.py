from fastapi import HTTPException
from src.repository.analytics_repository import AnalyticsRepository
from src.shared.utils.logger import logger
from datetime import datetime, date
from uuid import UUID
from .dtos import CategoryAnalyticsResponse, AccumulatedAnalyticsResponse, TrendAnalyticsResponse

class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    def get_expenses_by_category(self, user_id: int, start_date: date, end_date: date) -> list[CategoryAnalyticsResponse]:
        results = self.repository.get_expenses_by_category(user_id, start_date, end_date)
        return [
            CategoryAnalyticsResponse(
                category_name=row.category_name,
                category_color=row.category_color,
                total=row.total / 100.0 if row.total else 0.0
            ) for row in results
        ]

    def get_accumulated_expenses(self, user_id: int, start_date: date, end_date: date, group_by: str) -> list[AccumulatedAnalyticsResponse]:
        if group_by not in ["day", "week"]:
            raise HTTPException(status_code=422, detail="group_by deve ser 'day' ou 'week'")
            
        results = self.repository.get_accumulated_expenses(user_id, start_date, end_date, group_by)
        
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
        self, user_id: int, month: int, year: int, category_codes: list[str] | None = None
    ) -> list[TrendAnalyticsResponse]:
        if month == 1:
            prev_month = 12
            prev_year = year - 1
        else:
            prev_month = month - 1
            prev_year = year

        # Resolve category_codes if they are given as strings, the repository compares UUIDs
        codes = [UUID(c) for c in category_codes] if category_codes else None

        current_res, prev_res = self.repository.get_trend_by_category(
            user_id, month, year, prev_month, prev_year, codes
        )

        category_map = {}
        for row in current_res:
            category_map[row.category_code] = {
                "name": row.category_name,
                "color": row.category_color,
                "current": row.total / 100.0 if row.total else 0.0,
                "previous": 0.0
            }
            
        for row in prev_res:
            if row.category_code not in category_map:
                category_map[row.category_code] = {
                    "name": row.category_name,
                    "color": row.category_color,
                    "current": 0.0,
                    "previous": row.total / 100.0 if row.total else 0.0
                }
            else:
                category_map[row.category_code]["previous"] = row.total / 100.0 if row.total else 0.0

        response = []
        for code, data in category_map.items():
            curr = data["current"]
            prev = data["previous"]
            
            if curr > prev:
                trend = "up"
            elif curr < prev:
                trend = "down"
            else:
                trend = "stable"
                
            response.append(TrendAnalyticsResponse(
                category_name=data["name"],
                category_color=data["color"],
                current_total=curr,
                previous_total=prev,
                trend=trend
            ))
            
        return response
