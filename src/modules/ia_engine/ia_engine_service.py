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
import base64
import json
from datetime import datetime, timezone

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

## Dados e conta (OBRIGATÓRIO):
- Você só tem acesso a informações da **conta ativa desta sessão**. \
Nunca assuma dados de outras contas e nunca misture contexto entre usuários distintos.
- Para afirmar **qualquer valor monetário, saldo, contagem ou lista de lançamentos**, \
você DEVE usar a ferramenta adequada (`get_user_transactions`, `get_financial_summary`, etc.) \
**OU** basear-se exclusivamente no bloco de contexto numérico injetado pelo sistema, \
e somente quando o período e o tipo de dado corresponderem exatamente.
- **É terminantemente proibido inventar** valores em reais, quantidades ou nomes de \
lançamentos que não tenham sido fornecidos por uma ferramenta ou pelo bloco de contexto.
- Se não tiver os dados necessários para responder com precisão, chame a ferramenta \
adequada ou peça esclarecimentos ao usuário antes de responder.

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
- **create_transaction — parâmetro `amount`:** use sempre string no formato brasileiro \
(ex.: \"166,03\") ou número em **reais** com decimais (ex.: 166.03). Não envie o valor \
em centavos como inteiro isolado (ex.: 16603), pois o sistema pode confundir com reais inteiros.
"""

# ---------------------------------------------------------------------------
# Constantes de sessão Redis
# ---------------------------------------------------------------------------
CHAT_SESSION_KEY_PREFIX = "chat:session:"
CHAT_SESSION_TTL = 7 * 24 * 60 * 60  # 7 dias em segundos

# ---------------------------------------------------------------------------
# Constantes de processamento de imagem
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})

RECEIPT_EXTRACTION_PROMPT = """Você é um assistente de extração de dados de notas fiscais.
Analise a imagem da nota fiscal e retorne EXCLUSIVAMENTE um JSON válido com o seguinte schema:

{
  "confidence": "high" | "low" | "none",
  "establishment_name": string | null,
  "date": "YYYY-MM-DD" | null,
  "total": integer | null,
  "discount_total": integer | null,
  "items": [{"name": string, "unit_price": integer, "quantity": number}] | null
}

Regras:
- "total" = valor líquido final em centavos (após qualquer desconto).
- "confidence": "high" se o total estiver nítido; "low" se duvidoso; "none" se ilegível.
- Não invente valores. Se não conseguir extrair um campo, use null.
- Responda SOMENTE o JSON, sem texto adicional, sem markdown.
"""


def _build_receipt_synthetic_message(extracted: dict, filename: str, confidence: str) -> str:
    """
    Monta a mensagem textual (sem bytes) enviada ao chat_stream com os dados
    extraídos da nota fiscal, para que o modelo use create_transaction normalmente.
    """
    def fmt(cents: int | None) -> str:
        if cents is None:
            return "?"
        sign = "-" if cents < 0 else ""
        abs_c = abs(cents)
        return f"{sign}R$ {abs_c // 100:,}.{abs_c % 100:02d}".replace(",", ".")

    def amount_tool_hint(cents: int | None) -> str:
        """Instrução explícita para create_transaction (evita int centavos × reais inteiros)."""
        if cents is None:
            return (
                "\n\nIMPORTANTE (create_transaction): use `amount` como string em pt-BR "
                "ou número float em reais — não como inteiro em centavos."
            )
        c = abs(cents)
        br = f"{c // 100},{c % 100:02d}"
        reais_f = c / 100.0
        return (
            f"\n\nIMPORTANTE (create_transaction): use `amount` como string \"{br}\" "
            f"ou número {reais_f:.2f} em reais — **não** o valor em centavos como inteiro "
            f"({cents})."
        )

    name = extracted.get("establishment_name") or "não identificado"
    date_str = extracted.get("date") or "hoje"
    total = extracted.get("total")
    discount = extracted.get("discount_total")
    items: list[dict] = extracted.get("items") or []

    if confidence == "low":
        return (
            f"[Conciliação de nota fiscal — dados parciais]\n"
            f"Consegui extrair alguns dados, mas com baixa confiança:\n"
            f"- Total identificado: {fmt(total)} (pode estar incorreto)\n"
            f"- Estabelecimento: {name}\n"
            f"- Data: {date_str}\n\n"
            f"Antes de registrar, confirmas que o total de {fmt(total)} está correto "
            f"e qual a categoria mais adequada? Aguardo tua confirmação."
            f"{amount_tool_hint(total if isinstance(total, int) else None)}"
        )

    items_lines = "\n".join(
        f"- {item['name']} — {fmt(item.get('unit_price'))} x {item.get('quantity', 1)}"
        for item in items
    ) or "- (itens não identificados)"

    discount_line = f"Desconto aplicado: {fmt(discount)}\n" if discount else ""

    return (
        f"[Conciliação de nota fiscal]\n"
        f"Estabelecimento: {name}\n"
        f"Data da compra: {date_str}\n"
        f"Total líquido: {fmt(total)}\n"
        f"{discount_line}"
        f"\nItens identificados:\n{items_lines}\n\n"
        f"Por favor, registra essa compra como transação de despesa, usando a categoria "
        f'mais adequada para "{name}", marcando como paga (is_paid=true) e com a data '
        f"informada acima. Na descrição, inclua a lista completa de itens com seus preços."
        f"{amount_tool_hint(total if isinstance(total, int) else None)}"
    )


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

        Isolamento de conta (P0):
          - account_id é sempre derivado do JWT via get_current_account_id no controller.
          - O histórico Redis usa a chave chat:session:{user_id}:{account_id}, garantindo
            que cada par usuário+conta tenha seu próprio histórico sem compartilhamento.
          - O resumo de contexto é obtido exclusivamente para o account_id desta requisição.

        Injeção de contexto (Opção A):
          - O bloco de resumo numérico é concatenado ao system prompt apenas no array
            enviado ao provedor neste turno; o Redis persiste somente as mensagens
            user/assistant/tool, sem duplicar o contexto dinâmico a cada salvamento.
        """
        session = self._load_session(user_id, account_id)

        # Enriquecer system prompt com resumo numérico da conta (somente para este turno).
        # Falhas silenciosas: log de warning, chat prossegue sem o bloco de contexto.
        context_block = self._build_account_context(account_id, transactions_service)
        if context_block:
            enhanced_system = CHAT_SYSTEM_PROMPT + "\n\n" + context_block
            session[0] = {"role": "system", "content": enhanced_system}

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

        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in IMAGE_EXTENSIONS:
            async for event in self._process_receipt_upload(
                user_id=user_id,
                account_id=account_id,
                message=message,
                filename=filename,
                raw_bytes=raw_bytes,
                content_type=content_type or "image/jpeg",
                transactions_service=transactions_service,
                categories_service=categories_service,
                subscriptions_service=subscriptions_service,
                analytics_service=analytics_service,
            ):
                yield event
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

    async def _process_receipt_upload(
        self,
        user_id: int,
        account_id: int,
        message: str,
        filename: str,
        raw_bytes: bytes,
        content_type: str,
        transactions_service: TransactionsService,
        categories_service: CategoriesService,
        subscriptions_service: SubscriptionsService,
        analytics_service: AnalyticsService,
    ):
        """
        Fluxo de conciliação de nota fiscal via imagem.
        Extrai dados com chamada de visão e delega ao chat_stream para
        acionar create_transaction. A imagem nunca é persistida no Redis.
        """
        yield {"type": "status", "status": "thinking", "label": "Lendo a nota fiscal..."}

        extracted = self._extract_receipt_data(raw_bytes, content_type)
        confidence = extracted.get("confidence", "none")

        if confidence == "none":
            response = (
                "Não consegui ler a nota fiscal. "
                "Por favor, tente uma foto mais nítida e bem iluminada, "
                "preferencialmente com boa resolução e sem reflexos."
            )
            for chunk in self._chunk_text(response):
                yield {"type": "token", "token": chunk}
                await asyncio.sleep(0)
            # Persiste no Redis apenas o texto, nunca os bytes da imagem
            session = self._load_session(user_id, account_id)
            session.append({"role": "user", "content": message or f"[Imagem: {filename}]"})
            session.append({"role": "assistant", "content": response})
            self._save_session(user_id, account_id, session)
            return

        synthetic_message = _build_receipt_synthetic_message(extracted, filename, confidence)

        async for event in self.chat_stream(
            user_id=user_id,
            account_id=account_id,
            message=synthetic_message,
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

    @staticmethod
    def _build_account_context(
        account_id: int,
        transactions_service: TransactionsService,
    ) -> str:
        """
        Monta bloco de contexto numérico da conta para o prompt do turno atual.

        Obtém o resumo do mês/ano corrente via TransactionsService.get_summary, que
        reutiliza o cache Redis existente (sem custo adicional de banco na maioria dos
        casos). O account_id é exclusivamente o da sessão ativa — nunca aceitar outro.

        Retorna string vazia em caso de falha, sem interromper o stream.
        """
        try:
            now = datetime.now(timezone.utc)
            summary = transactions_service.get_summary(
                account_id=account_id,
                month=now.month,
                year=now.year,
            )

            def fmt(cents: int) -> str:
                sign = "-" if cents < 0 else ""
                abs_cents = abs(cents)
                reais = abs_cents // 100
                centavos = abs_cents % 100
                return f"{sign}R$ {reais:,}.{centavos:02d}".replace(",", ".")

            return (
                f"### Contexto numérico da conta ({now.month:02d}/{now.year})\n"
                f"- Receitas totais: {fmt(summary.total_income)}\n"
                f"- Despesas totais: {fmt(summary.total_expense)}\n"
                f"- Saldo líquido geral: {fmt(summary.net_balance)}\n"
                f"- Receitas realizadas (pagas): {fmt(summary.paid_income)}\n"
                f"- Despesas realizadas (pagas): {fmt(summary.paid_expense)}\n"
                f"- Saldo realizado (pago): {fmt(summary.paid_net_balance)}\n"
                f"_Fonte: dados reais da conta ativa. "
                f"Para detalhes ou outros períodos, use as ferramentas disponíveis._"
            )
        except Exception as exc:
            logger.warning(
                f"[ia_engine] Falha ao montar contexto numérico para account_id={account_id}: {exc}"
            )
            return ""

    def _extract_receipt_data(self, raw_bytes: bytes, content_type: str) -> dict:
        """
        Executa chamada de visão ao LLM para extração estruturada de dados de nota fiscal.
        Retorna dict com confidence, total, itens etc.
        Em caso de falha, retorna {"confidence": "none"} sem propagar exceção.
        A imagem (base64) é transmitida ao LLM mas nunca persistida.
        """
        try:
            b64 = base64.b64encode(raw_bytes).decode("utf-8")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{content_type};base64,{b64}"},
                        },
                        {"type": "text", "text": RECEIPT_EXTRACTION_PROMPT},
                    ],
                }
            ]
            result = self.ia.create_chat(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1024,
            )
            if not isinstance(result, dict):
                logger.warning("[ia_engine] _extract_receipt_data: resposta não é dict")
                return {"confidence": "none"}
            if result.get("confidence") not in {"high", "low", "none"}:
                result["confidence"] = "low"
            return result
        except Exception as exc:
            logger.warning(f"[ia_engine] Falha na extração de nota fiscal: {exc}")
            return {"confidence": "none"}

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
