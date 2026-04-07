"""
ia_engine_controller.py — Router FastAPI do módulo IA Engine.

Endpoints:
  - POST /ia/chat         → Chat streaming via SSE
  - POST /ia/chat/upload  → Chat com upload de arquivos (imagens, OFX)
  - DELETE /ia/chat       → Limpa sessão de chat
  - POST /ia/ofx/import   → Inicia importação OFX em background
  - GET  /ia/ofx/status   → Consulta status da última importação
  - GET  /ia/ofx/{code}   → Consulta status de importação específica
"""

import json
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from src.modules.analytics.analytics_service import AnalyticsService
from src.modules.categories.categories_service import CategoriesService
from src.modules.ia_engine.ia_engine_service import IaEngineService
from src.modules.subscriptions.subscriptions_service import SubscriptionsService
from src.modules.transactions.transactions_service import TransactionsService
from src.shared.services.di_services import ContainerService
from src.shared.utils.auth import get_current_user
from src.shared.utils.dependencies import get_current_account_id

from .dtos import OfxImportResponse

router = APIRouter(prefix="/ia", tags=["IA Engine"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".ofx"}


# ------------------------------------------------------------------
# Chat Streaming (SSE)
# ------------------------------------------------------------------
@router.post(
    "/chat",
    summary="Envia mensagem ao assistente IA (resposta streaming via SSE)",
)
@inject
async def chat_stream(
    message: str = Form(...),
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: IaEngineService = Depends(Provide[ContainerService.ia_engine_service]),
    transactions_service: TransactionsService = Depends(
        Provide[ContainerService.transactions_service]
    ),
    categories_service: CategoriesService = Depends(
        Provide[ContainerService.categories_service]
    ),
    subscriptions_service: SubscriptionsService = Depends(
        Provide[ContainerService.subscriptions_service]
    ),
    analytics_service: AnalyticsService = Depends(
        Provide[ContainerService.analytics_service]
    ),
):
    async def event_generator():
        async for event in service.chat_stream(
            user_id=current_user["uid"],
            account_id=account_id,
            message=message,
            transactions_service=transactions_service,
            categories_service=categories_service,
            subscriptions_service=subscriptions_service,
            analytics_service=analytics_service,
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/chat/upload",
    summary="Envia mensagem + arquivo ao assistente IA (streaming SSE)",
)
@inject
async def chat_with_upload(
    message: str = Form(""),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: IaEngineService = Depends(Provide[ContainerService.ia_engine_service]),
    transactions_service: TransactionsService = Depends(
        Provide[ContainerService.transactions_service]
    ),
    categories_service: CategoriesService = Depends(
        Provide[ContainerService.categories_service]
    ),
    subscriptions_service: SubscriptionsService = Depends(
        Provide[ContainerService.subscriptions_service]
    ),
    analytics_service: AnalyticsService = Depends(
        Provide[ContainerService.analytics_service]
    ),
):
    filename = file.filename or "upload.bin"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extensão não permitida. Aceitos: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo excede o limite de 10 MB",
        )

    async def event_generator():
        async for event in service.chat_upload_stream(
            user_id=current_user["uid"],
            account_id=account_id,
            message=message,
            filename=filename,
            content_type=file.content_type,
            raw_bytes=raw_bytes,
            transactions_service=transactions_service,
            categories_service=categories_service,
            subscriptions_service=subscriptions_service,
            analytics_service=analytics_service,
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------
# Limpar Sessão de Chat
# ------------------------------------------------------------------
@router.delete(
    "/chat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Limpa o histórico de chat da sessão atual",
)
@inject
async def clear_chat(
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: IaEngineService = Depends(Provide[ContainerService.ia_engine_service]),
):
    service.clear_chat_session(current_user["uid"], account_id)


# ------------------------------------------------------------------
# OFX Import (Background)
# ------------------------------------------------------------------
@router.post(
    "/ofx/import",
    response_model=OfxImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Inicia importação OFX em background com classificação IA",
)
@inject
async def import_ofx(
    file: UploadFile = File(...),
    source: str = Form("settings"),
    current_user: dict = Depends(get_current_user),
    account_id: int = Depends(get_current_account_id),
    service: IaEngineService = Depends(Provide[ContainerService.ia_engine_service]),
):
    filename = file.filename or "upload.ofx"
    if not filename.lower().endswith(".ofx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Apenas arquivos .ofx são aceitos",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo excede o limite de 10 MB",
        )

    result = service.start_ofx_import(
        user_id=current_user["uid"],
        account_id=account_id,
        filename=filename,
        raw_bytes=raw_bytes,
        source=source,
    )
    return result


# ------------------------------------------------------------------
# OFX Import Status
# ------------------------------------------------------------------
@router.get(
    "/ofx/status",
    response_model=OfxImportResponse | None,
    summary="Retorna o status da importação OFX mais recente",
)
@inject
async def get_latest_import_status(
    account_id: int = Depends(get_current_account_id),
    service: IaEngineService = Depends(Provide[ContainerService.ia_engine_service]),
):
    return service.get_latest_import(account_id)


@router.get(
    "/ofx/{code}",
    response_model=OfxImportResponse,
    summary="Retorna o status de uma importação OFX específica",
)
@inject
async def get_import_status(
    code: UUID,
    account_id: int = Depends(get_current_account_id),
    service: IaEngineService = Depends(Provide[ContainerService.ia_engine_service]),
):
    result = service.get_import_status(account_id, code)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Importação não encontrada",
        )
    return result
