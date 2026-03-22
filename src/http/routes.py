"""
src/http/routes.py — Agregador central de routers.

Regra: este arquivo NÃO deve conter lógica de rota.
Apenas importa e inclui os routers dos módulos.
"""

from fastapi import APIRouter

from src.modules.health.health_controller import router as health_router
from src.modules.users.users_controller import router as users_router
from src.modules.auth.auth_controller import router as auth_router
from src.modules.transactions.transactions_controller import router as transactions_router
from src.modules.categories.categories_controller import router as categories_router
from src.modules.analytics.analytics_controller import router as analytics_router
from src.modules.planning.planning_controller import router as planning_router
from src.modules.subscriptions.subscriptions_controller import router as subscriptions_router

router = APIRouter()

router.include_router(health_router)
router.include_router(users_router)
router.include_router(auth_router)
router.include_router(transactions_router)
router.include_router(categories_router)
router.include_router(analytics_router)
router.include_router(planning_router)
router.include_router(subscriptions_router)