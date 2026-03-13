"""
Utilitários de autenticação JWT — Monettra.

Dependências: python-jose[cryptography] passlib[bcrypt]
Variáveis de ambiente: JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
"""

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.shared.utils.environment import environment

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
SECRET_KEY = environment.get("JWT_SECRET_KEY", "changeme-in-production")
ALGORITHM = environment.get("JWT_ALGORITHM", "HS256")
EXPIRE_MINUTES = int(environment.get("JWT_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Hashing de senhas
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Retorna o hash bcrypt da senha informada."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha plaintext corresponde ao hash armazenado."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# Geração e decodificação de tokens
# ---------------------------------------------------------------------------

def create_access_token(data: dict) -> str:
    """
    Gera um JWT assinado com os dados fornecidos e tempo de expiração.

    Args:
        data: Payload do token.
              Deve conter ao mínimo:
              - "sub": str(user_code)  — UUID público do usuário
              - "uid": int(user_id)    — PK interna do usuário
              - "type": str             — role do usuário

    Returns:
        Token JWT como string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decodifica e valida um JWT.

    Raises:
        HTTPException(401): Se o token for inválido ou expirado.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado"
        )


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    FastAPI Dependency — valida o token JWT e retorna o payload do usuário.

    Returns:
        dict com os campos:
        - "sub" (str): user_code (UUID público)
        - "uid" (int): user_id (PK interna — elimina a necessidade de busca no banco)
        - "type" (str): role do usuário

    Raises:
        HTTPException(401): Se o token for inválido, expirado ou ausente.
    """
    token = credentials.credentials
    payload = decode_token(token)

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: campo 'sub' ausente"
        )

    if payload.get("uid") is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: campo 'uid' ausente"
        )

    return payload


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI Dependency — garante que o usuário é do tipo 'admin'.

    Raises:
        HTTPException(403): Se o usuário não for admin.
    """
    if current_user.get("type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores"
        )
    return current_user
