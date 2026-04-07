"""
Testes unitários para IaEngineService.

Casos cobertos (v0.14):
  - Caso 4: historico_redis_isolado_por_account_id
  - Caso 5: get_summary_somente_account_id_sessao
  - Caso 3: resumo_injetado_coerente_com_get_summary

Casos cobertos (v0.15 — conciliação de nota fiscal por imagem):
  - test_extract_receipt_data_retorna_none_confidence_em_falha
  - test_build_receipt_synthetic_message_high_confidence
  - test_build_receipt_synthetic_message_low_confidence
  - test_build_receipt_synthetic_message_sem_itens
  - test_build_receipt_synthetic_message_desconto_presente
  - test_build_receipt_synthetic_message_data_nula_usa_hoje
  - test_imagem_nao_persiste_base64_no_redis
"""

from unittest.mock import MagicMock, patch

import pytest

from src.modules.ia_engine.ia_engine_service import (
    CHAT_SESSION_KEY_PREFIX,
    IaEngineService,
    _build_receipt_synthetic_message,
)
from src.modules.transactions.dtos import TransactionSummaryResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def summary_mock() -> TransactionSummaryResponse:
    return TransactionSummaryResponse(
        total_income=500_000,   # R$ 5.000,00
        total_expense=200_000,  # R$ 2.000,00
        net_balance=300_000,    # R$ 3.000,00
        paid_income=400_000,    # R$ 4.000,00
        paid_expense=150_000,   # R$ 1.500,00
        paid_net_balance=250_000,  # R$ 2.500,00
    )


@pytest.fixture
def transactions_service_mock(summary_mock: TransactionSummaryResponse) -> MagicMock:
    service = MagicMock()
    service.get_summary.return_value = summary_mock
    return service


# ---------------------------------------------------------------------------
# Caso 4: historico_redis_isolado_por_account_id
# ---------------------------------------------------------------------------

def test_session_key_includes_user_and_account():
    """
    A chave de sessão Redis deve ser exclusiva por (user_id, account_id),
    garantindo que usuários distintos e contas distintas tenham históricos isolados.
    """
    key_a = IaEngineService._session_key(user_id=1, account_id=10)
    key_b = IaEngineService._session_key(user_id=1, account_id=20)
    key_c = IaEngineService._session_key(user_id=2, account_id=10)

    assert key_a != key_b, "Contas diferentes do mesmo usuário devem ter chaves distintas"
    assert key_a != key_c, "Usuários diferentes com a mesma conta devem ter chaves distintas"
    assert key_b != key_c


def test_session_key_format():
    """A chave deve seguir o padrão chat:session:{user_id}:{account_id}."""
    key = IaEngineService._session_key(user_id=7, account_id=42)
    assert key == f"{CHAT_SESSION_KEY_PREFIX}7:42"
    assert key.startswith("chat:session:")


# ---------------------------------------------------------------------------
# Caso 5: get_summary_somente_account_id_sessao
# ---------------------------------------------------------------------------

def test_build_account_context_uses_session_account_id(
    transactions_service_mock: MagicMock,
    summary_mock: TransactionSummaryResponse,
):
    """
    _build_account_context deve chamar get_summary com exatamente o account_id
    fornecido, sem alterar ou substituir pelo ID de outra conta.
    """
    result = IaEngineService._build_account_context(
        account_id=99,
        transactions_service=transactions_service_mock,
    )

    call_kwargs = transactions_service_mock.get_summary.call_args
    assert call_kwargs is not None, "get_summary deve ter sido chamado"
    assert call_kwargs.kwargs["account_id"] == 99, (
        "account_id passado ao get_summary deve ser o da sessão ativa"
    )
    assert result != "", "Deve retornar um bloco não-vazio em caso de sucesso"


# ---------------------------------------------------------------------------
# Caso 3: resumo_injetado_coerente_com_get_summary
# ---------------------------------------------------------------------------

def test_build_account_context_contains_expected_fields(
    transactions_service_mock: MagicMock,
    summary_mock: TransactionSummaryResponse,
):
    """
    O bloco de contexto deve conter os campos do TransactionSummaryResponse
    formatados em BRL e o cabeçalho com o período mês/ano correto.
    """
    with patch(
        "src.modules.ia_engine.ia_engine_service.datetime"
    ) as mock_dt:
        mock_now = MagicMock()
        mock_now.month = 4
        mock_now.year = 2026
        mock_dt.now.return_value = mock_now

        result = IaEngineService._build_account_context(
            account_id=1,
            transactions_service=transactions_service_mock,
        )

    assert "04/2026" in result, "O período deve aparecer no cabeçalho do bloco"
    assert "R$ 5.000.00" in result, "total_income deve estar formatado em BRL"
    assert "R$ 2.000.00" in result, "total_expense deve estar formatado em BRL"
    assert "R$ 3.000.00" in result, "net_balance deve estar formatado em BRL"
    assert "R$ 4.000.00" in result, "paid_income deve estar formatado em BRL"
    assert "R$ 1.500.00" in result, "paid_expense deve estar formatado em BRL"
    assert "R$ 2.500.00" in result, "paid_net_balance deve estar formatado em BRL"


def test_build_account_context_returns_empty_on_failure():
    """
    Falha em get_summary não deve propagar exceção — retorna string vazia
    e registra warning, mantendo o chat funcional.
    """
    broken_service = MagicMock()
    broken_service.get_summary.side_effect = Exception("DB unavailable")

    result = IaEngineService._build_account_context(
        account_id=1,
        transactions_service=broken_service,
    )

    assert result == "", "Em caso de erro, deve retornar string vazia (sem propagar exceção)"


def test_build_account_context_negative_balance(
    transactions_service_mock: MagicMock,
):
    """Saldos negativos devem ser formatados com sinal de menos."""
    transactions_service_mock.get_summary.return_value = TransactionSummaryResponse(
        total_income=100_000,
        total_expense=300_000,
        net_balance=-200_000,
        paid_income=50_000,
        paid_expense=200_000,
        paid_net_balance=-150_000,
    )

    result = IaEngineService._build_account_context(
        account_id=1,
        transactions_service=transactions_service_mock,
    )

    assert "-R$ 2.000.00" in result, "Saldo negativo deve exibir sinal de menos"
    assert "-R$ 1.500.00" in result, "Saldo realizado negativo deve exibir sinal de menos"


# ---------------------------------------------------------------------------
# Testes v0.15 — Conciliação de nota fiscal por imagem
# ---------------------------------------------------------------------------

def _make_ia_engine_service(ia_mock: MagicMock) -> IaEngineService:
    """Instancia IaEngineService com dependências mínimas para testes unitários."""
    service = IaEngineService.__new__(IaEngineService)
    service.ia = ia_mock
    service.cache = MagicMock()
    service.ofx_import_repository = MagicMock()
    return service


def test_extract_receipt_data_retorna_none_confidence_em_falha():
    """
    Caso 8: se create_chat levantar exceção, _extract_receipt_data deve retornar
    {"confidence": "none"} sem propagar a exceção.
    """
    ia_mock = MagicMock()
    ia_mock.create_chat.side_effect = Exception("timeout")
    service = _make_ia_engine_service(ia_mock)

    result = service._extract_receipt_data(b"fake_bytes", "image/jpeg")

    assert result == {"confidence": "none"}, (
        "Falha de create_chat deve retornar confidence=none silenciosamente"
    )


def test_extract_receipt_data_retorna_none_confidence_quando_resposta_invalida():
    """Se create_chat retornar None ou não-dict, deve retornar {"confidence": "none"}."""
    ia_mock = MagicMock()
    ia_mock.create_chat.return_value = None
    service = _make_ia_engine_service(ia_mock)

    result = service._extract_receipt_data(b"fake", "image/png")

    assert result == {"confidence": "none"}


def test_extract_receipt_data_normaliza_confidence_invalida():
    """Se confidence retornada não for high/low/none, deve normalizar para 'low'."""
    ia_mock = MagicMock()
    ia_mock.create_chat.return_value = {
        "confidence": "maybe",
        "total": 5000,
    }
    service = _make_ia_engine_service(ia_mock)

    result = service._extract_receipt_data(b"img", "image/webp")

    assert result["confidence"] == "low"


def test_build_receipt_synthetic_message_high_confidence():
    """
    Caso 1/4: mensagem high confidence deve conter estabelecimento, total formatado
    e instrução de create_transaction com is_paid=true.
    """
    extracted = {
        "confidence": "high",
        "establishment_name": "Supermercado Atacadão",
        "date": "2026-04-06",
        "total": 15_750,  # R$ 157,50
        "discount_total": None,
        "items": [
            {"name": "Arroz 5kg", "unit_price": 2_990, "quantity": 1},
            {"name": "Feijão 1kg", "unit_price": 750, "quantity": 2},
        ],
    }

    result = _build_receipt_synthetic_message(extracted, "nota.jpg", "high")

    assert "Supermercado Atacadão" in result
    assert "R$ 157.50" in result
    assert "is_paid=true" in result
    assert "Arroz 5kg" in result
    assert "Feijão 1kg" in result
    assert "2026-04-06" in result
    assert "IMPORTANTE (create_transaction)" in result
    assert '"157,50"' in result or "157,50" in result


def test_build_receipt_synthetic_message_low_confidence():
    """
    Caso 6: mensagem low confidence deve pedir confirmação ao usuário
    e não emitir instrução de create_transaction diretamente.
    """
    extracted = {
        "confidence": "low",
        "establishment_name": "Farmácia Popular",
        "date": None,
        "total": 8_000,
        "discount_total": None,
        "items": None,
    }

    result = _build_receipt_synthetic_message(extracted, "nota.png", "low")

    assert "baixa confiança" in result
    assert "confirmas" in result.lower() or "confirmação" in result.lower() or "Confirmas" in result
    assert "is_paid=true" not in result


def test_build_receipt_synthetic_message_sem_itens():
    """
    Caso unitário: items=None não deve lançar exceção e deve exibir
    placeholder "(itens não identificados)".
    """
    extracted = {
        "confidence": "high",
        "establishment_name": "Loja X",
        "date": "2026-04-01",
        "total": 3_000,
        "discount_total": None,
        "items": None,
    }

    result = _build_receipt_synthetic_message(extracted, "nota.jpg", "high")

    assert "(itens não identificados)" in result


def test_build_receipt_synthetic_message_desconto_presente():
    """Caso 3: quando discount_total presente, linha de desconto deve aparecer na mensagem."""
    extracted = {
        "confidence": "high",
        "establishment_name": "Mercado Fiel",
        "date": "2026-04-06",
        "total": 10_000,    # R$ 100,00 líquido
        "discount_total": 2_000,  # R$ 20,00 de desconto
        "items": [],
    }

    result = _build_receipt_synthetic_message(extracted, "nota.jpg", "high")

    assert "Desconto aplicado" in result
    assert "R$ 20.00" in result


def test_build_receipt_synthetic_message_data_nula_usa_hoje():
    """Caso 5: quando date=None, a mensagem deve conter 'hoje' como fallback."""
    extracted = {
        "confidence": "high",
        "establishment_name": "Posto Shell",
        "date": None,
        "total": 20_000,
        "discount_total": None,
        "items": [],
    }

    result = _build_receipt_synthetic_message(extracted, "nota.jpg", "high")

    assert "hoje" in result


def test_imagem_nao_persiste_base64_no_redis():
    """
    Caso 7 (P0): quando confidence=none, a sessão salva no Redis deve conter
    apenas texto — nunca bytes de imagem ou conteúdo base64.
    """
    ia_mock = MagicMock()
    service = _make_ia_engine_service(ia_mock)

    # Simula _extract_receipt_data retornando confidence=none
    service._extract_receipt_data = MagicMock(return_value={"confidence": "none"})
    # Simula cache vazio (sessão nova)
    service.cache.get.return_value = None

    captured_sessions: list[str] = []

    def fake_set(key: str, value: str, ttl: int = 0) -> None:
        captured_sessions.append(value)

    service.cache.set = fake_set

    import asyncio

    async def run():
        events = []
        async for event in service._process_receipt_upload(
            user_id=1,
            account_id=10,
            message="",
            filename="nota.jpg",
            raw_bytes=b"\xff\xd8\xff" * 100,  # bytes simulados de imagem
            content_type="image/jpeg",
            transactions_service=MagicMock(),
            categories_service=MagicMock(),
            subscriptions_service=MagicMock(),
            analytics_service=MagicMock(),
        ):
            events.append(event)
        return events

    asyncio.run(run())

    assert captured_sessions, "save_session deve ter sido chamado"
    saved_json = captured_sessions[0]
    assert "base64" not in saved_json, "base64 não deve aparecer na sessão Redis"
    assert "\xff" not in saved_json, "bytes brutos não devem aparecer na sessão Redis"
    # Confirma que é JSON serializável (texto puro)
    import json
    parsed = json.loads(saved_json)
    assert isinstance(parsed, list)
