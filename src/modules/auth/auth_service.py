"""
AuthService — Regras de negócio de autenticação.
"""

from uuid import UUID

from fastapi import HTTPException, status

from src.repository.user_repository import UserRepository
from src.shared.utils.logger import logger
from src.shared.utils.auth import create_access_token, hash_password, verify_password
from .dtos import RegisterDTO, LoginDTO


class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, data: RegisterDTO):
        """
        Registra um novo usuário com senha hasheada (bcrypt).

        Raises:
            HTTPException(422): Senha com menos de 8 caracteres.
            HTTPException(409): E-mail já cadastrado.
        """
        if len(data.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A senha deve ter no mínimo 8 caracteres"
            )

        if self.repository.find_by_email(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="E-mail já cadastrado"
            )

        try:
            user = self.repository.create({
                "name": data.name,
                "email": data.email,
                "password": hash_password(data.password),
            })

            return user
        except Exception as e:
            logger.error(f"Erro ao registrar usuário: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro interno ao registrar usuário"
            )

    def login(self, data: LoginDTO) -> dict:
        """
        Valida credenciais e retorna um JWT.

        Raises:
            HTTPException(401): Credenciais inválidas.
        """
        user = self.repository.find_by_email(data.email)
        if not user or not verify_password(data.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciais inválidas"
            )

        token = create_access_token({
            "sub": str(user.code),
            "uid": user.id,
            "type": user.type.value
        })
        return {"access_token": token, "token_type": "bearer"}

    def get_by_code(self, user_code: str):
        """
        Busca um usuário pelo code (UUID).

        Raises:
            HTTPException(404): Usuário não encontrado.
        """
        user = self.repository.find_by_code(user_code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        return user
