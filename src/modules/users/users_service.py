from fastapi import HTTPException

from src.repository.user_repository import UserRepository
from src.modules.users.dtos import UpdateUserDTO, UserResponse
from src.shared.utils.logger import logger
from src.shared.utils.auth import hash_password

class UsersService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def find_all(self) -> list[UserResponse]:
        try:
            users = self.repository.find_all()
            return [UserResponse.model_validate(u) for u in users]
        except Exception as e:
            logger.error(f"Erro ao buscar usuários: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao buscar usuários")

    def update(self, user_code: str, payload: UpdateUserDTO, requester: dict) -> UserResponse:
        user = self.repository.find_by_code(user_code)

        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        requester_type = requester.get("type")
        requester_sub = str(requester.get("sub"))

        if requester_type != "admin" and requester_sub != str(user.code):
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para atualizar este usuário"
            )

        try:
            payload = payload.model_dump(exclude_none=True)

            if payload.get("password") is not None:
                payload["password"] = hash_password(payload["password"])

            updated = self.repository.update(user, payload)
            return UserResponse.model_validate(updated)
        except Exception as e:
            logger.error(f"Erro ao atualizar usuário {user_code}: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao atualizar usuário")

    def deactivate(self, user_code: str) -> UserResponse:
        user = self.repository.find_by_code(user_code)

        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        try:
            deactivated = self.repository.deactivate(user)
            return UserResponse.model_validate(deactivated)
        except Exception as e:
            logger.error(f"Erro ao desativar usuário {user_code}: {e}")
            raise HTTPException(status_code=500, detail="Erro interno ao desativar usuário")
