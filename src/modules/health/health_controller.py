from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from dependency_injector.wiring import Provide, inject

from src.shared.services.di_services import ContainerService
from src.shared.utils.logger import logger

router = APIRouter(tags=["Health"])


@router.get("/ping", summary="Verifica se a API está no ar")
def ping():
    return {"status": "ok", "message": "pong"}


@router.get("/db/health", summary="Verifica a conexão com o banco de dados")
@inject
def db_health(session_factory=Depends(Provide[ContainerService.db])):
    try:
        # ContainerService.db é um Factory que retorna o sessionmaker.
        # Precisamos chamar session_factory() para obter uma Session real.
        session: Session = session_factory()
        session.execute(text("SELECT 1"))
        session.close()
        return {"status": "ok", "message": "Banco de dados conectado"}
    except Exception as e:
        logger.error(f"Erro ao conectar no banco: {e}")
        raise HTTPException(
            status_code=500,
            detail="Falha na conexão com o banco de dados"
        )
