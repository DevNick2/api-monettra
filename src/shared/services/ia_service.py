"""
IaService — Serviço compartilhado de comunicação com LLMs.

Interface agnóstica a provedor. Configurável via variáveis de ambiente:
  - OPENROUTER_API_KEY : chave de API do OpenRouter
  - OPENROUTER_MODEL   : modelo a usar (default: openrouter/free)

Features:
  - Retry resiliente com backoff exponencial
  - Timeout adequado para chamadas longas
  - Parsing seguro de JSON (previne "string indices must be integers")
  - Streaming via SSE (Server-Sent Events)
"""

import json
import asyncio
from typing import Any, AsyncGenerator

from openai import OpenAI
from src.shared.utils.environment import environment
from src.shared.utils.logger import logger


# ---------------------------------------------------------------------------
# Configuração de retry
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
BASE_DELAY = 1.0   # segundos
TIMEOUT = 120       # segundos


class IaService:
    def __init__(self):
        api_key = environment.get("OPENROUTER_API_KEY")
        self._model = environment.get("OPENROUTER_MODEL", "openrouter/free")

        try:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                timeout=TIMEOUT,
            )
            logger.info(
                f"IA conectada — modelo: {self._model}"
            )
        except Exception as e:
            logger.warning(f"IA indisponível: {e} — IA desativada")
            self.client = None

    @property
    def model(self) -> str:
        return self._model

    # ------------------------------------------------------------------
    # Chat síncrono (com retry + backoff)
    # ------------------------------------------------------------------
    # XXX TODO :: Vamos por partes:
    # 1º O tool_choise sempre será auto, não precisa passar como parametro;
    # 2º O response_format sempre será {"type": "json_object"}, não precisa passar como parametro;
    # 3° O nome da variavel kwargs é ruim, vamos usar payload;
    # 4º O create_chat_stream usa uma estrutura com 70% de similaridade a essa, vamos refatorar para que seja DRY
    # 5º Sempre por default o ZDR é true, não precisa vir de variavel de ambiente
    def create_chat(
        self,
        messages: list,
        response_format: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        return_message: bool = False,
        with_financial_data: bool = True,
    ) -> dict | str | None:
        """
        Envia mensagens ao LLM e retorna a resposta parseada.

        Quando `response_format={"type": "json_object"}`, o retorno é um dict.
        Caso contrário, retorna a string bruta.
        Inclui retry com backoff exponencial para RemoteProtocolError.
        """
        if not self.client:
            logger.warning("IA: client não disponível — retornando None")
            return None

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "extra_headers": {"X-OpenRouter-Title": "Monettra"},
                }
                extra_body = self._build_extra_body(with_financial_data)
                if extra_body:
                    kwargs["extra_body"] = extra_body
                if response_format:
                    kwargs["response_format"] = response_format
                if tools:
                    kwargs["tools"] = tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice

                completion = self.client.chat.completions.create(**kwargs)
                message = completion.choices[0].message
                raw_content = message.content

                if return_message:
                    return message.model_dump()

                # Parsing seguro: tenta JSON se solicitado
                if response_format and response_format.get("type") in {
                    "json_object",
                    "json_schema",
                }:
                    return self._safe_parse_json(raw_content)

                return raw_content

            except Exception as e:
                last_error = e
                delay = BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"IA tentativa {attempt}/{MAX_RETRIES} falhou: {e} "
                    f"— retry em {delay}s"
                )
                if attempt < MAX_RETRIES:
                    import time
                    time.sleep(delay)

        logger.error(f"IA falhou após {MAX_RETRIES} tentativas: {last_error}")
        return None

    # ------------------------------------------------------------------
    # Chat com streaming (para SSE)
    # ------------------------------------------------------------------
    async def create_chat_stream(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        with_financial_data: bool = True,
    ) -> AsyncGenerator[str, None]:
        """
        Envia mensagens ao LLM e retorna um generator assíncrono de tokens
        para streaming via SSE.
        """
        if not self.client:
            yield "data: [IA indisponível]\n\n"
            return

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "extra_headers": {"X-OpenRouter-Title": "Monettra"},
                }
                extra_body = self._build_extra_body(with_financial_data)
                if extra_body:
                    kwargs["extra_body"] = extra_body

                stream = self.client.chat.completions.create(**kwargs)

                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content
                return  # stream concluído com sucesso

            except Exception as e:
                last_error = e
                delay = BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"IA stream tentativa {attempt}/{MAX_RETRIES} falhou: {e} "
                    f"— retry em {delay}s"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(delay)

        logger.error(
            f"IA stream falhou após {MAX_RETRIES} tentativas: {last_error}"
        )
        yield "[Erro: não foi possível obter resposta da IA]"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_parse_json(raw: str | None) -> dict | list | None:
        """
        Parse seguro de JSON retornado pelo LLM.
        Previne o erro 'string indices must be integers' garantindo
        que o resultado é sempre um dict/list.
        """
        if raw is None:
            return None
        try:
            # Remove possíveis marcadores de markdown (```json ... ```)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove primeira e última linha (```json e ```)
                lines = [
                    l for l in lines
                    if not l.strip().startswith("```")
                ]
                cleaned = "\n".join(lines)

            parsed = json.loads(cleaned)

            if isinstance(parsed, (dict, list)):
                return parsed

            logger.warning(
                f"IA retornou JSON com tipo inesperado: {type(parsed)}"
            )
            return None

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"IA: falha no parse JSON: {e} — raw: {raw[:200]}")
            return None

    @staticmethod
    def _build_extra_body(with_financial_data: bool) -> dict[str, Any] | None:
        if not with_financial_data:
            return None

        enabled = environment.get("OPENROUTER_ZDR_ENABLED", "true")
        if str(enabled).lower() in {"0", "false", "no"}:
            return None

        return {"provider": {"zdr": True}}
