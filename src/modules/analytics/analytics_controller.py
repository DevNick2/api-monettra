from fastapi import APIRouter, Depends, Query
from dependency_injector.wiring import Provide, inject
from datetime import date

from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.modules.analytics.analytics_service import AnalyticsService
from .dtos import CategoryAnalyticsResponse, AccumulatedAnalyticsResponse, TrendAnalyticsResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/by-category",
    response_model=list[CategoryAnalyticsResponse],
    summary="Gastos por categoria no mês"
)
@inject
async def get_by_category(
    start_date: date = Query(..., description="Data de Início"),
    end_date: date = Query(..., description="Data de Fim"),
    current_user: dict = Depends(get_current_user),
    service: AnalyticsService = Depends(Provide[ContainerService.analytics_service])
):
    return service.get_expenses_by_category(current_user["uid"], start_date, end_date)


@router.get(
    "/accumulated",
    response_model=list[AccumulatedAnalyticsResponse],
    summary="Acumulado do mês (dia ou semana)"
)
@inject
async def get_accumulated(
    start_date: date = Query(..., description="Data de Início"),
    end_date: date = Query(..., description="Data de Fim"),
    group_by: str = Query(..., description="'day' ou 'week'"),
    current_user: dict = Depends(get_current_user),
    service: AnalyticsService = Depends(Provide[ContainerService.analytics_service])
):
    return service.get_accumulated_expenses(current_user["uid"], start_date, end_date, group_by)


@router.get(
    "/trend-by-category",
    response_model=list[TrendAnalyticsResponse],
    summary="Tendência de categorias em relação ao mês anterior"
)
@inject
async def get_trend_by_category(
    month: int = Query(..., description="Mês"),
    year: int = Query(..., description="Ano"),
    category_codes: list[str] | None = Query(None, description="Lista opcional de UUIDs de categorias"),
    current_user: dict = Depends(get_current_user),
    service: AnalyticsService = Depends(Provide[ContainerService.analytics_service])
):
    return service.get_trend_by_category(current_user["uid"], month, year, category_codes)
