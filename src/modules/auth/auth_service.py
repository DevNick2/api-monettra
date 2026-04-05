"""
AuthService — Regras de negócio de autenticação.
"""

from uuid import UUID
from typing import TYPE_CHECKING

import httpx
import secrets

from fastapi import HTTPException, status

from src.repository.user_repository import UserRepository
from src.shared.utils.logger import logger
from src.shared.utils.auth import create_access_token, hash_password, verify_password
from src.shared.utils.environment import environment
from .dtos import RegisterDTO, LoginDTO, GoogleCallbackDTO

if TYPE_CHECKING:
    from src.modules.categories.categories_service import CategoriesService
    from src.modules.accounts.accounts_service import AccountsService
    from src.modules.accounts.dtos import CreateAccountDTO

# XXX FIXME :: Isso deveria estar em uma ENV
GOOGLE_TOKENINFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"


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

    # XXX TODO :: Esse método pode ser refatorado
    # Aqui temos dois problemas:
    # 1) Esta injetando outros services aqui: A ideia é que não haja dependências entre services, se houver, deve ser
    # feito na controller
    # 2) Esta duplicando o método de criação de conta e categorias em lote, podemos extrair
    # para um método privado e consumir tanto aqui quanto no /register
    def google_login(
        self,
        body: GoogleCallbackDTO,
        category_service: "CategoriesService",
        accounts_service: "AccountsService",
    ) -> dict:
        """
        Valida o id_token do Google, cria ou recupera o usuário no banco
        e retorna o JWT interno do Monettra.

        O frontend obteve o id_token via Google Sign-In na tela de login.
        Este endpoint NÃO substitui o fluxo email/senha — é um provedor adicional (Opção B).
        """
        # 1. Verificar token com Google
        try:
            response = httpx.get(GOOGLE_TOKENINFO_URL, params={"id_token": body.id_token}, timeout=10)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token do Google inválido"
                )
            google_data = response.json()
        except httpx.RequestError as e:
            logger.error(f"Erro de rede ao validar token Google: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Erro ao comunicar com o Google"
            )

        # 2. Extrair dados do usuário
        email = google_data.get("email")
        if not email or not google_data.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-mail do Google não verificado"
            )

        name = body.display_name or google_data.get("name") or email.split("@")[0]

        # 3. Upsert do usuário (criar se não existir)
        user = self.repository.find_by_email(email)
        is_new_user = False
        if not user:
            is_new_user = True
            # Senha aleatória — usuário OAuth não usa senha direta
            placeholder_password = hash_password(secrets.token_hex(32))
            user = self.repository.create({
                "name": name,
                "email": email,
                "password": placeholder_password,
            })

        # 4. Criar categorias e conta para novos usuários
        if is_new_user:
            from src.schemas.categories import DEFAULT_CATEGORIES
            from src.modules.accounts.dtos import CreateAccountDTO
            accounts_service.create_account(
                user.id,
                CreateAccountDTO(name=f"Conta de {user.name or user.email}")
            )
            account_id = accounts_service.repository.find_account_by_user(user.id).id
            category_service.create_in_lot(user.id, account_id, DEFAULT_CATEGORIES)

        # 5. Gerar e retornar JWT interno
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
