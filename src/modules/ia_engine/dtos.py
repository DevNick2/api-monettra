"""
ia_engine/dtos.py — DTOs do módulo de IA Engine.
"""

from datetime import datetime

from pydantic import UUID4, BaseModel


class ChatMessageDTO(BaseModel):
    """Mensagem enviada pelo usuário ao chat."""
    message: str


class ChatMessageResponse(BaseModel):
    """Resposta do chat (usado em modo não-streaming)."""
    role: str = "assistant"
    content: str

# XXX TODO :: Essa resposta deve ser movida para o módulo
# Settings
class OfxImportResponse(BaseModel):
    """Status de uma importação OFX em background."""
    code: UUID4
    filename: str
    status: str
    source: str = "settings"
    total_transactions: int | None = 0
    processed_transactions: int | None = 0
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
