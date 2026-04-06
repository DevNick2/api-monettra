"""
Testes unitários para IaEngineService.

Casos cobertos:
  - Caso 4: historico_redis_isolado_por_account_id
  - Caso 5: get_summary_somente_account_id_sessao
  - Caso 3: resumo_injetado_coerente_com_get_summary
"""

from unittest.mock import MagicMock, patch

import pytest

from src.modules.ia_engine.ia_engine_service import (
    CHAT_SESSION_KEY_PREFIX,
    IaEngineService,
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
