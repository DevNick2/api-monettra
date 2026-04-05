"""
IaEngineService — Regras de negócio do Motor de IA do Monettra.

Responsabilidades:
  - Gerenciar sessões de chat persistidas no Redis (TTL 7 dias)
  - Orquestrar tools com OpenRouter puro
  - Emitir eventos SSE estruturados para o frontend
  - Disparar processamento OFX em background via Celery
"""

from __future__ import annotations

import asyncio
import json

from fastapi import HTTPException, status

from src.modules.analytics.analytics_service import AnalyticsService
from src.modules.categories.categories_service import CategoriesService
from src.modules.ia_engine.dtos import OfxImportResponse
from src.modules.subscriptions.subscriptions_service import SubscriptionsService
from src.modules.transactions.transactions_service import TransactionsService
from src.repository.ofx_import_repository import OfxImportRepository
from src.shared.services.ia_service import IaService
from src.shared.services.ia_tasks import process_ofx_task
from src.shared.services.ia_tools import IaToolRegistry
from src.shared.services.redis_service import RedisService
from src.shared.utils.logger import logger


# ---------------------------------------------------------------------------
# System Prompts com Guardrails
# ---------------------------------------------------------------------------
CHAT_SYSTEM_PROMPT = """Você é o **Escriba Real do Monettra**, um assistente financeiro pessoal \
inteligente e sábio, inspirado nos escribas da antiga Babilônia.

## Suas Capacidades (APENAS estas):
1. **Diagnóstico financeiro**: responder perguntas sobre fluxo de caixa, saldos, tendências \
e hábitos de gasto do usuário.
2. **Revisão de transações**: orientar sobre criação, edição, classificação e gerenciamento \
de transações financeiras.
3. **Classificação e ingestão**: ajudar a entender notas fiscais, prints de compras e \
arquivos OFX importados.
4. **Educação financeira**: oferecer dicas e insights baseados nos princípios de gestão \
financeira pessoal.
5. **Operações assistidas**: quando necessário, você pode consultar ferramentas do sistema \
e criar transações, categorias e assinaturas com base nos dados fornecidos pelo usuário.

## Guardrails (OBRIGATÓRIO):
- Você **NÃO PODE** executar comandos de sistema, acessar IoT, ou tratar de temas \
fora do domínio financeiro pessoal.
- Se o usuário perguntar algo fora do escopo, responda educadamente: \
"Sou especializado em finanças pessoais. Posso te ajudar com diagnósticos financeiros, \
transações e classificações."
- Responda SEMPRE em **português brasileiro (pt-BR)**.
- Seja claro, conciso e profissional. Use formatação markdown quando apropriado.
- NUNCA revele dados internos como IDs sequenciais do banco de dados. \
Use apenas códigos UUID quando precisar referenciar entidades.
- Quando existir uma tool apropriada, prefira usá-la em vez de supor dados.
- Se faltarem parâmetros para criar algo, peça esclarecimentos antes de executar.
"""

# ---------------------------------------------------------------------------
# Constantes de sessão Redis
# ---------------------------------------------------------------------------
CHAT_SESSION_KEY_PREFIX = "chat:session:"
CHAT_SESSION_TTL = 7 * 24 * 60 * 60  # 7 dias em segundos


class IaEngineService:
    def __init__(
        self,
        ia: IaService,
        ofx_import_repository: OfxImportRepository,
        cache: RedisService,
    ):
        self.ia = ia
        self.ofx_import_repository = ofx_import_repository
        self.cache = cache

    # ------------------------------------------------------------------
    # Chat Streaming
    # ------------------------------------------------------------------
    async def chat_stream(
        self,
        user_id: int,
        account_id: int,
        message: str,
        transactions_service: TransactionsService,
        categories_service: CategoriesService,
        subscriptions_service: SubscriptionsService,
        analytics_service: AnalyticsService,
    ):
        """
        Processa mensagem do usuário e retorna eventos SSE estruturados.
        Mantém histórico de sessão no Redis com TTL de 7 dias.

        Os services de domínio são recebidos por parâmetro (injetados pela controller)
        para evitar dependência circular entre services de módulos distintos.
        """
        session = self._load_session(user_id, account_id)
        registry = IaToolRegistry(
            transactions_service=transactions_service,
            categories_service=categories_service,
            subscriptions_service=subscriptions_service,
            analytics_service=analytics_service,
        )

        session.append({"role": "user", "content": message})
        session = self._trim_session(session)

        yield {
            "type": "status",
            "status": "thinking",
            "label": "Lendo teu pedido...",
        }

        assistant_message = self.ia.create_chat(
            messages=session,
            tools=registry.get_definitions(),
            tool_choice="auto",
            temperature=0.2,
            max_tokens=1536,
            return_message=True,
        )

        if not assistant_message:
            yield {
                "type": "error",
                "message": (
                    "O Escriba Real não está disponível neste momento. "
                    "Tente novamente em instantes."
                ),
            }
            return

        tool_calls = assistant_message.get("tool_calls") or []
        loop_count = 0

        while tool_calls and loop_count < 5:
            loop_count += 1
            session.append(self._assistant_message_to_history(assistant_message))

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                arguments = self._parse_tool_arguments(tool_call["function"].get("arguments"))
                tool_label = registry.get_label(tool_name) or f"Consultando {tool_name}..."

                yield {
                    "type": "tool_started",
                    "tool_name": tool_name,
                    "label": tool_label,
                }

                try:
                    result = registry.execute(
                        tool_name=tool_name,
                        arguments=arguments,
                        user_id=user_id,
                        account_id=account_id,
                    )
                except HTTPException as exc:
                    result = {
                        "tool_name": tool_name,
                        "tool_label": tool_label,
                        "result_text": str(exc.detail),
                        "result_for_model": {
                            "error": True,
                            "message": str(exc.detail),
                            "tool_name": tool_name,
                        },
                    }
                except Exception as exc:
                    logger.error(f"Erro inesperado na tool '{tool_name}': {exc}")
                    result = {
                        "tool_name": tool_name,
                        "tool_label": tool_label,
                        "result_text": "Houve um problema ao acessar as tábuas do arquivo.",
                        "result_for_model": {
                            "error": True,
                            "message": f"Erro interno: {str(exc)}",
                            "tool_name": tool_name,
                        },
                    }

                yield {
                    "type": "tool_finished",
                    "tool_name": tool_name,
                    "label": result.get("tool_label") or f"{tool_name} concluída.",
                    "result_text": result.get("result_text"),
                }

                if result.get("ui_block"):
                    yield {
                        "type": "ui_block",
                        "tool_name": tool_name,
                        "block": result["ui_block"],
                    }

                session.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_name,
                    "content": json.dumps(
                        result.get("result_for_model", {}),
                        ensure_ascii=False,
                    ),
                })

            assistant_message = self.ia.create_chat(
                messages=session,
                tools=registry.get_definitions(),
                tool_choice="auto",
                temperature=0.2,
                max_tokens=1536,
                return_message=True,
            )

            if not assistant_message:
                yield {
                    "type": "error",
                    "message": (
                        "O Escriba Real perdeu o fio do raciocínio após usar as ferramentas. "
                        "Tente novamente."
                    ),
                }
                return

            tool_calls = assistant_message.get("tool_calls") or []

        if tool_calls:
            yield {
                "type": "status",
                "status": "warning",
                "label": "Limite de encadeamento de tools atingido. Finalizando resposta.",
            }

        final_content = (assistant_message.get("content") or "").strip()

        yield {
            "type": "status",
            "status": "responding",
            "label": "Redigindo tua resposta...",
        }

        if final_content:
            for chunk in self._chunk_text(final_content):
                yield {"type": "token", "token": chunk}
                await asyncio.sleep(0)
            session.append({"role": "assistant", "content": final_content})
        else:
            full_response: list[str] = []
            async for token in self.ia.create_chat_stream(messages=session):
                full_response.append(token)
                yield {"type": "token", "token": token}

            assistant_content = "".join(full_response).strip()
            if not assistant_content:
                yield {
                    "type": "error",
                    "message": "Resposta vazia recebida da IA. Tente reformular o pedido.",
                }
                return
            session.append({"role": "assistant", "content": assistant_content})

        self._save_session(user_id, account_id, session)

    async def chat_upload_stream(
        self,
        user_id: int,
        account_id: int,
        message: str,
        filename: str,
        content_type: str | None,
        raw_bytes: bytes,
        transactions_service: TransactionsService,
        categories_service: CategoriesService,
        subscriptions_service: SubscriptionsService,
        analytics_service: AnalyticsService,
    ):
        safe_context = (
            "[Arquivo processado internamente]\n"
            f"- nome: {filename}\n"
            f"- tipo: {content_type or 'desconhecido'}\n"
            f"- tamanho_kb: {round(len(raw_bytes) / 1024, 1)}"
        )

        if filename.lower().endswith(".ofx"):
            import_record = self.start_ofx_import(
                user_id=user_id,
                account_id=account_id,
                filename=filename,
                raw_bytes=raw_bytes,
                source="chat",
            )
            yield {
                "type": "import_status",
                "import": self._serialize_import_record(import_record),
            }
            response = (
                "Recebi teu arquivo OFX e enviei a conciliação para processamento "
                "em segundo plano. Acompanhe o status aqui no chat ou na área de "
                "configurações."
            )
            for chunk in self._chunk_text(response):
                yield {"type": "token", "token": chunk}
                await asyncio.sleep(0)
            session = self._load_session(user_id, account_id)
            session.append({"role": "user", "content": message or safe_context})
            session.append({"role": "assistant", "content": response})
            self._save_session(user_id, account_id, session)
            return

        combined_message = message.strip()
        if combined_message:
            combined_message = f"{combined_message}\n\n{safe_context}"
        else:
            combined_message = safe_context

        async for event in self.chat_stream(
            user_id=user_id,
            account_id=account_id,
            message=combined_message,
            transactions_service=transactions_service,
            categories_service=categories_service,
            subscriptions_service=subscriptions_service,
            analytics_service=analytics_service,
        ):
            yield event

    def clear_chat_session(self, user_id: int, account_id: int) -> None:
        """Limpa o histórico de chat de uma sessão."""
        key = self._session_key(user_id, account_id)
        self.cache.delete(key)

    # ------------------------------------------------------------------
    # OFX Import — Celery Background Processing
    # ------------------------------------------------------------------
    def start_ofx_import(
        self,
        user_id: int,
        account_id: int,
        filename: str,
        raw_bytes: bytes,
        source: str = "settings",
    ) -> dict:
        """
        Inicia o processamento OFX via Celery (worker separado).
        Retorna 409 se já houver uma importação em andamento para a conta.
        Retorna o registro de importação (com code UUID para polling).
        """
        active = self.ofx_import_repository.find_active_by_account(account_id)
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Já existe uma importação em andamento para esta conta. "
                    "Aguarde a conclusão antes de enviar um novo arquivo."
                ),
            )

        import_record = self.ofx_import_repository.create({
            "filename": filename,
            "status": "pending",
            "source": source,
            "user_id": user_id,
            "account_id": account_id,
        })

        process_ofx_task.delay(
            import_code=str(import_record.code),
            user_id=user_id,
            account_id=account_id,
            raw_bytes_hex=raw_bytes.hex(),
        )

        logger.info(
            f"OFX Import {import_record.code}: task enviada ao Celery worker "
            f"— conta={account_id}, arquivo={filename}, origem={source}"
        )

        return import_record

    # ------------------------------------------------------------------
    # Consulta de Status OFX
    # ------------------------------------------------------------------
    def get_import_status(self, account_id: int, import_code) -> dict | None:
        """Consulta o status de uma importação OFX."""
        return self.ofx_import_repository.find_by_code(import_code, account_id)

    def get_latest_import(self, account_id: int) -> dict | None:
        """Retorna a importação OFX mais recente da conta."""
        return self.ofx_import_repository.find_latest_by_account(account_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _session_key(user_id: int, account_id: int) -> str:
        return f"{CHAT_SESSION_KEY_PREFIX}{user_id}:{account_id}"

    def _load_session(self, user_id: int, account_id: int) -> list[dict]:
        """Carrega sessão de chat do Redis. Cria nova sessão se não existir."""
        key = self._session_key(user_id, account_id)
        raw = self.cache.get(key)
        if raw:
            try:
                messages = json.loads(raw)
                if isinstance(messages, list):
                    return [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + messages
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning(f"Chat session {key}: falha ao carregar do Redis — {exc}")
        return [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    def _save_session(self, user_id: int, account_id: int, session: list[dict]) -> None:
        """Persiste sessão de chat no Redis (sem o system prompt, que é injetado no load)."""
        key = self._session_key(user_id, account_id)
        messages_without_system = [m for m in session if m.get("role") != "system"]
        try:
            self.cache.set(
                key,
                json.dumps(messages_without_system, ensure_ascii=False),
                ttl=CHAT_SESSION_TTL,
            )
        except Exception as exc:
            logger.warning(f"Chat session {key}: falha ao salvar no Redis — {exc}")

    @staticmethod
    def _trim_session(session: list[dict]) -> list[dict]:
        """Limita o histórico a 50 mensagens preservando o system prompt."""
        if len(session) > 52:
            system = session[0]
            return [system] + session[-50:]
        return session

    @staticmethod
    def _assistant_message_to_history(message: dict) -> dict:
        payload = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        if message.get("tool_calls"):
            payload["tool_calls"] = [
                {
                    "id": item["id"],
                    "type": item["type"],
                    "function": {
                        "name": item["function"]["name"],
                        "arguments": item["function"]["arguments"],
                    },
                }
                for item in message["tool_calls"]
            ]
        return payload

    @staticmethod
    def _parse_tool_arguments(raw_arguments: str | None) -> dict:
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        words = text.split(" ")
        chunks: list[str] = []
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            chunks.append(f"{word}{suffix}")
        return chunks

    @staticmethod
    def _serialize_import_record(record) -> dict:
        return OfxImportResponse.model_validate(record).model_dump(mode="json")
