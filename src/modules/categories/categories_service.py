"""
CategoriesService — Regras de negócio do módulo de categorias.
"""

from uuid import UUID

from fastapi import HTTPException, status

from src.repository.category_repository import CategoryRepository
from src.shared.utils.logger import logger
from .dtos import CreateCategoryDTO, UpdateCategoryDTO
import asyncio
from src.schemas.transactions import TransactionType

class CategoriesService:
    def __init__(self, repository: CategoryRepository):
        self.repository = repository

    def find_all(self, account_id: int) -> list:
        return self.repository.find_all_by_account(account_id)

    def show(self, account_id: int, code: str):
        try:
            category = self.repository.find_by_code(code, account_id)

            return category
        except Exception as e:
            logger.error(f"Erro ao buscar categoria: {e}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada"
            )

    def create(self, user_id: int, account_id: int, data: CreateCategoryDTO):
        try:
            return self.repository.create({
                "title": data.title,
                "color": data.color,
                "icon_name": data.icon_name,
                "user_id": user_id,
                "account_id": account_id,
                "type": TransactionType[data.type.upper()]
            })
        except Exception as e:
            logger.error(f"Erro ao criar categoria: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar categoria"
            )
    def create_in_lot(self, user_id: int, account_id: int, data: list[dict]):
        try:
            for cat in data:
                self.create(user_id, account_id, CreateCategoryDTO(**cat))
        except Exception as e:
            logger.error(f"Erro ao criar categoria em lote: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao criar categoria em lote"
            )

    def update(self, account_id: int, category_code: UUID, data: UpdateCategoryDTO):
        category = self.repository.find_by_code(category_code, account_id)

        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada")

        if data.title is not None:
            category.title = data.title
        if data.color is not None:
            category.color = data.color
        if data.icon_name is not None:
            category.icon_name = data.icon_name
        if data.type is not None:
            category.type = TransactionType[data.type.upper()]

        return self.repository.update(category)

    def remove(self, account_id: int, category_code: UUID):
        category = self.repository.find_by_code(category_code, account_id)

        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada")

        self.repository.soft_delete(category)
