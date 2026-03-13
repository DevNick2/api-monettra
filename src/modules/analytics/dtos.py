from pydantic import BaseModel

class CategoryAnalyticsResponse(BaseModel):
    category_name: str
    category_color: str
    total: float

class AccumulatedAnalyticsResponse(BaseModel):
    label: str
    total: float

class TrendAnalyticsResponse(BaseModel):
    category_name: str
    category_color: str
    current_total: float
    previous_total: float
    trend: str
