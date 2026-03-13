from datetime import date
from fastapi import HTTPException, status
from src.repository.planning_repository import PlanningRepository
from src.repository.category_repository import CategoryRepository
from src.repository.transaction_repository import TransactionRepository
from src.modules.planning.dtos import CreatePlanningEntryDTO, UpdatePlanningEntryDTO, PlanningEntryResponse, PlanningHorizonResponse, PlanningHorizonMonthlyData
from src.modules.categories.dtos import CategoryResponse
from src.shared.services.redis_service import RedisService
from src.schemas.categories import CategorySchema

class PlanningService:
    def __init__(
        self, 
        repository: PlanningRepository, 
        transaction_repository: TransactionRepository,
        cache: RedisService
    ):
        self.repository = repository
        self.transaction_repository = transaction_repository
        self.cache = cache
        
    def _map_entry_to_response(self, entry) -> PlanningEntryResponse:
        cat_resp = None
        if entry.category:
            cat_resp = CategoryResponse(
                code=entry.category.code,
                title=entry.category.title,
                color=entry.category.color,
                icon_name=entry.category.icon_name,
                created_at=entry.category.created_at
            )
            
        return PlanningEntryResponse(
            code=entry.code,
            title=entry.title,
            amount=str(entry.amount),
            type=entry.type,
            category=cat_resp,
            is_materialized=entry.is_materialized,
            materialized_transaction_code=entry.materialized_transaction_code,
            due_date=str(entry.due_date),
            description=entry.description,
            group_code=entry.group_code,
            installment_index=entry.installment_index,
            installment_total=entry.installment_total,
            created_at=entry.created_at
        )

    def create(self, user_id: int, payload: CreatePlanningEntryDTO, category = None) -> list[PlanningEntryResponse]:
        cat_id = category.id if category else None
        entries = self.repository.create_entry(user_id, payload, cat_id)
        return [self._map_entry_to_response(e) for e in entries]
        
    def find_all(self, user_id: int, start_date: date | None = None, end_date: date | None = None) -> list[PlanningEntryResponse]:
        entries = self.repository.find_all_by_user(user_id, start_date, end_date)
        return [self._map_entry_to_response(e) for e in entries]

    def update(self, user_id: int, code: str, payload: UpdatePlanningEntryDTO, category = None) -> list[PlanningEntryResponse]:
        entry = self.repository.find_by_code(code, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Provisão não encontrada")
            
        cat_id = category.id if category else None
            
        updated_entries = self.repository.update_entry(user_id, payload, entry, cat_id)
        return [self._map_entry_to_response(e) for e in updated_entries]

    def delete(self, user_id: int, code: str, scope: str) -> None:
        entry = self.repository.find_by_code(code, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Provisão não encontrada")
            
        self.repository.delete_entry(user_id, entry, scope)
        
    def materialize(self, user_id: int, code: str) -> PlanningEntryResponse:
        entry = self.repository.find_by_code(code, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Provisão não encontrada")
            
        if entry.is_materialized:
            raise HTTPException(status_code=400, detail="Esta provisão já foi materializada")
            
        # Create real transaction
        tx_data = {
            "title": entry.title,
            "description": entry.description,
            "amount": entry.amount,
            "type": entry.type.name.lower() if hasattr(entry.type, 'name') else str(entry.type),
            "due_date": entry.due_date,
            "is_paid": False,
            "user_id": user_id,
        }
        if entry.category_id:
            tx_data["category_id"] = entry.category_id
            
        tx = self.transaction_repository.create(tx_data)
        
        # Invalidate cache for transactions since we added one
        cache_pattern = f"transactions:{user_id}:*"
        self.cache.delete_pattern(cache_pattern)
        
        # update planning entry
        updated_entry = self.repository.materialize_entry(entry, tx.code)
        return self._map_entry_to_response(updated_entry)

    def horizon(self, user_id: int, start_date: date, end_date: date) -> PlanningHorizonResponse:
        results = self.repository.find_horizon(user_id, start_date, end_date)
        mapped = [PlanningHorizonMonthlyData(**r) for r in results]
        return PlanningHorizonResponse(horizon=mapped)
