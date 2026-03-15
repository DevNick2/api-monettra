from datetime import date
from fastapi import HTTPException, status
from src.repository.category_repository import CategoryRepository
from src.repository.transaction_repository import TransactionRepository
from src.modules.planning.dtos import PlanningEntryResponse
from src.modules.categories.dtos import CategoryResponse
from src.shared.services.redis_service import RedisService
from src.schemas.categories import CategorySchema

class PlanningService:
    def __init__(
        self, 
        transaction_repository: TransactionRepository,
        cache: RedisService
    ):
        self.transaction_repository = transaction_repository
        self.cache = cache

    def horizon(self, user_id: int):
        results = self.transaction_repository.horizon(user_id)

        return results
