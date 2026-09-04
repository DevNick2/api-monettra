"""
Testes unitários — TransactionsService
Cobertura:
  - v0.8: _resolve_paid_status_for_manual_date (helper puro)
  - v0.8: create() aplica regra de data automaticamente
  - v0.8: update() recalcula is_paid ao trocar data
  - v0.9: get_summary() retorna e cacheia TransactionSummaryResponse
  - v0.18: duplicate() e duplicate_month() — duplicação de lançamentos
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.modules.transactions.transactions_service import (
    TransactionsService,
    _resolve_paid_status_for_manual_date,
)
from src.modules.transactions.dtos import (
    CreateTransactionDTO,
    UpdateTransactionDTO,
    DuplicateTransactionDTO,
    DuplicateMonthDTO,
    TransactionSummaryResponse,
)
from src.schemas.transactions import TransactionType, TransactionClassification
from src.shared.services.ia_tools import normalize_llm_transaction_amount


# ──────────────────────────────────────────────────────────────────────────────
# Helper puro: _resolve_paid_status_for_manual_date
# ──────────────────────────────────────────────────────────────────────────────

def test_resolve_paid_today_is_paid():
    today = date.today()
    assert _resolve_paid_status_for_manual_date(today, today) is True


def test_resolve_paid_yesterday_is_paid():
    from datetime import timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)
    assert _resolve_paid_status_for_manual_date(yesterday, today) is True


def test_resolve_paid_tomorrow_is_pending():
    from datetime import timedelta
    today = date.today()
    tomorrow = today + timedelta(days=1)
    assert _resolve_paid_status_for_manual_date(tomorrow, today) is False


def test_resolve_paid_far_past_is_paid():
    today = date.today()
    past = date(2020, 1, 1)
    assert _resolve_paid_status_for_manual_date(past, today) is True


def test_normalize_llm_transaction_amount_centavos_tipo_receipt():
    """Inteiro 16603 (centavos) → float reais para CreateTransactionDTO."""
    assert normalize_llm_transaction_amount(16603) == 166.03


def test_normalize_llm_transaction_amount_reais_inteiros_pequenos():
    """166 reais inteiros permanece int (DTO faz ×100)."""
    assert normalize_llm_transaction_amount(166) == 166


def test_normalize_llm_transaction_amount_string_inalterado():
    assert normalize_llm_transaction_amount("166,03") == "166,03"


def test_create_transaction_dto_com_amount_normalizado_receipt():
    """Fluxo LLM: 16603 centavos → normaliza → 16603 centavos no modelo."""
    payload = CreateTransactionDTO(
        title="Nota",
        amount=normalize_llm_transaction_amount(16603),
        type="expense",
        due_date=date(2026, 3, 21),
    )
    assert payload.amount == 16603


def test_resolve_paid_far_future_is_pending():
    today = date.today()
    future = date(2099, 12, 31)
    assert _resolve_paid_status_for_manual_date(future, today) is False


# ──────────────────────────────────────────────────────────────────────────────
# TransactionsService.create — regra de data aplicada ao criar
# ──────────────────────────────────────────────────────────────────────────────

def _make_service():
    mock_repo = MagicMock()
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    mock_ia = MagicMock()
    service = TransactionsService(
        repository=mock_repo,
        cache=mock_cache,
        ia=mock_ia,
    )
    return service, mock_repo, mock_cache


def test_create_past_date_forces_is_paid():
    service, mock_repo, _ = _make_service()
    mock_repo.create.return_value = MagicMock()

    from datetime import timedelta
    past_date = date.today() - timedelta(days=5)
    payload = CreateTransactionDTO(
        title="Teste",
        amount=1000,
        type="expense",
        due_date=past_date,
        is_paid=False,  # usuário enviou False, mas deve ser overridden
    )

    service.create(user_id=1, account_id=1, data=payload)

    call_kwargs = mock_repo.create.call_args[0][0]
    assert call_kwargs["is_paid"] is True
    assert call_kwargs["paid_at"] is not None


def test_create_today_forces_is_paid():
    service, mock_repo, _ = _make_service()
    mock_repo.create.return_value = MagicMock()

    payload = CreateTransactionDTO(
        title="Hoje",
        amount=500,
        type="income",
        due_date=date.today(),
    )

    service.create(user_id=1, account_id=1, data=payload)

    call_kwargs = mock_repo.create.call_args[0][0]
    assert call_kwargs["is_paid"] is True


def test_create_future_date_stays_pending():
    service, mock_repo, _ = _make_service()
    mock_repo.create.return_value = MagicMock()

    from datetime import timedelta
    future_date = date.today() + timedelta(days=10)
    payload = CreateTransactionDTO(
        title="Futuro",
        amount=200,
        type="expense",
        due_date=future_date,
        is_paid=True,  # usuário enviou True, mas deve ser overridden para False
    )

    service.create(user_id=1, account_id=1, data=payload)

    call_kwargs = mock_repo.create.call_args[0][0]
    assert call_kwargs["is_paid"] is False
    assert call_kwargs["paid_at"] is None


# ──────────────────────────────────────────────────────────────────────────────
# TransactionsService.update — recalcula ao mudar data
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_transaction(due_date=None, is_paid=False, recurrence_id=None):
    t = MagicMock()
    t.due_date = due_date or date.today()
    t.is_paid = is_paid
    t.paid_at = None
    t.recurrence_id = recurrence_id
    return t


def test_update_date_to_past_sets_paid():
    service, mock_repo, _ = _make_service()
    from datetime import timedelta
    past = date.today() - timedelta(days=3)
    mock_transaction = _make_mock_transaction()
    mock_repo.find_by_code.return_value = mock_transaction
    mock_repo.update.return_value = mock_transaction

    payload = UpdateTransactionDTO(due_date=past, scope="single")
    service.update(account_id=1, transaction_code="some-uuid", data=payload, category=None)

    assert mock_transaction.is_paid is True
    assert mock_transaction.paid_at is not None


def test_update_date_to_future_sets_pending():
    service, mock_repo, _ = _make_service()
    from datetime import timedelta
    future = date.today() + timedelta(days=10)
    mock_transaction = _make_mock_transaction(is_paid=True)
    mock_repo.find_by_code.return_value = mock_transaction
    mock_repo.update.return_value = mock_transaction

    payload = UpdateTransactionDTO(due_date=future, scope="single")
    service.update(account_id=1, transaction_code="some-uuid", data=payload, category=None)

    assert mock_transaction.is_paid is False
    assert mock_transaction.paid_at is None


def test_update_without_date_change_respects_is_paid():
    """Sem mudança de data, is_paid explícito do payload é usado."""
    service, mock_repo, _ = _make_service()
    mock_transaction = _make_mock_transaction(is_paid=False)
    mock_repo.find_by_code.return_value = mock_transaction
    mock_repo.update.return_value = mock_transaction

    payload = UpdateTransactionDTO(is_paid=True, scope="single")
    service.update(account_id=1, transaction_code="some-uuid", data=payload, category=None)

    assert mock_transaction.is_paid is True


# ──────────────────────────────────────────────────────────────────────────────
# TransactionsService.get_summary — retorno e cache
# ──────────────────────────────────────────────────────────────────────────────

def test_get_summary_cache_miss_calls_repository():
    service, mock_repo, mock_cache = _make_service()
    mock_cache.get.return_value = None
    mock_repo.get_summary_by_account.return_value = {
        "total_income": 5000,
        "total_expense": 3000,
        "net_balance": 2000,
        "paid_income": 4000,
        "paid_expense": 2000,
        "paid_net_balance": 2000,
    }

    result = service.get_summary(account_id=1, month=4, year=2026)

    mock_repo.get_summary_by_account.assert_called_once_with(1, month=4, year=2026)
    assert isinstance(result, TransactionSummaryResponse)
    assert result.net_balance == 2000
    assert result.paid_net_balance == 2000


def test_get_summary_cache_hit_skips_repository():
    service, mock_repo, mock_cache = _make_service()
    cached_data = {
        "total_income": 1000,
        "total_expense": 500,
        "net_balance": 500,
        "paid_income": 800,
        "paid_expense": 400,
        "paid_net_balance": 400,
    }
    mock_cache.get.return_value = json.dumps(cached_data)

    result = service.get_summary(account_id=1, month=4, year=2026)

    mock_repo.get_summary_by_account.assert_not_called()
    assert result.total_income == 1000
    assert result.paid_net_balance == 400


def test_get_summary_empty_month_returns_zeros():
    service, mock_repo, mock_cache = _make_service()
    mock_cache.get.return_value = None
    mock_repo.get_summary_by_account.return_value = {
        "total_income": 0,
        "total_expense": 0,
        "net_balance": 0,
        "paid_income": 0,
        "paid_expense": 0,
        "paid_net_balance": 0,
    }

    result = service.get_summary(account_id=1, month=1, year=2026)
    assert result.net_balance == 0
    assert result.paid_net_balance == 0


# ──────────────────────────────────────────────────────────────────────────────
# TransactionsService.duplicate — duplicação de lançamento individual (v0.18)
# ──────────────────────────────────────────────────────────────────────────────

def _make_original_transaction(**overrides):
    defaults = dict(
        account_id=1,
        title="Aluguel",
        amount=150000,
        type=TransactionType.EXPENSE,
        description="Aluguel mensal",
        category_id=5,
        owner_id=7,
        subscription_id=None,
        invoice_id=None,
        due_date=date(2026, 7, 10),
    )
    defaults.update(overrides)
    t = MagicMock()
    for key, value in defaults.items():
        setattr(t, key, value)
    return t


def test_duplicate_transaction_creates_copy_with_chosen_date_unpaid():
    """Cenário 1 — duplicar item: cópia nasce com a data escolhida e is_paid=False."""
    service, mock_repo, _ = _make_service()
    original = _make_original_transaction()
    mock_repo.find_by_code_ignore_account.return_value = original
    mock_repo.create.return_value = MagicMock()

    payload = DuplicateTransactionDTO(due_date=date(2026, 8, 15))
    service.duplicate(user_id=2, account_id=1, transaction_code="some-uuid", data=payload)

    call_kwargs = mock_repo.create.call_args[0][0]
    assert call_kwargs["due_date"] == date(2026, 8, 15)
    assert call_kwargs["is_paid"] is False
    assert call_kwargs["paid_at"] is None
    assert call_kwargs["title"] == "Aluguel"
    assert call_kwargs["amount"] == 150000
    assert call_kwargs["created_by"] == 2
    assert call_kwargs["owner_id"] == 7


def test_duplicate_subscription_or_invoice_transaction_becomes_standalone():
    """Cenário 2 — duplicar lançamento de assinatura/fatura vira avulso (DEFAULT)."""
    service, mock_repo, _ = _make_service()
    original = _make_original_transaction(subscription_id=42, invoice_id=None)
    mock_repo.find_by_code_ignore_account.return_value = original
    mock_repo.create.return_value = MagicMock()

    payload = DuplicateTransactionDTO(due_date=date(2026, 9, 1))
    service.duplicate(user_id=1, account_id=1, transaction_code="some-uuid", data=payload)

    call_kwargs = mock_repo.create.call_args[0][0]
    assert call_kwargs["type_of_transaction"] == TransactionClassification.DEFAULT
    assert call_kwargs["subscription_id"] is None
    assert call_kwargs["invoice_id"] is None
    assert call_kwargs["recurrence_id"] is None


def test_duplicate_endpoints_reject_transaction_outside_active_account():
    """Account isolation — transação de outra conta deve retornar 403."""
    service, mock_repo, _ = _make_service()
    other_account_transaction = _make_original_transaction(account_id=99)
    mock_repo.find_by_code_ignore_account.return_value = other_account_transaction

    payload = DuplicateTransactionDTO(due_date=date(2026, 8, 1))
    with pytest.raises(HTTPException) as exc_info:
        service.duplicate(user_id=1, account_id=1, transaction_code="some-uuid", data=payload)

    assert exc_info.value.status_code == 403


def test_duplicate_raises_404_when_transaction_not_found():
    service, mock_repo, _ = _make_service()
    mock_repo.find_by_code_ignore_account.return_value = None

    payload = DuplicateTransactionDTO(due_date=date(2026, 8, 1))
    with pytest.raises(HTTPException) as exc_info:
        service.duplicate(user_id=1, account_id=1, transaction_code="some-uuid", data=payload)

    assert exc_info.value.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# TransactionsService.duplicate_month — duplicação em lote (v0.18)
# ──────────────────────────────────────────────────────────────────────────────

def test_duplicate_month_copies_only_default_transactions_unpaid():
    """Cenário 3 — duplicar mês: repositório já filtra DEFAULT; cópias nascem is_paid=False."""
    service, mock_repo, _ = _make_service()
    t1 = _make_original_transaction(title="Mercado", amount=20000, due_date=date(2026, 7, 10))
    t2 = _make_original_transaction(title="Aluguel", amount=150000, due_date=date(2026, 7, 5))
    mock_repo.find_default_by_month.return_value = [t1, t2]
    mock_repo.bulk_create.return_value = [MagicMock(), MagicMock()]

    payload = DuplicateMonthDTO(source_month=7, source_year=2026, target_month=8, target_year=2026)
    result = service.duplicate_month(user_id=1, account_id=1, data=payload)

    mock_repo.find_default_by_month.assert_called_once_with(1, 7, 2026)
    records = mock_repo.bulk_create.call_args[0][0]
    assert len(records) == 2
    assert all(r["is_paid"] is False and r["paid_at"] is None for r in records)
    assert all(r["type_of_transaction"] == TransactionClassification.DEFAULT for r in records)
    assert all(r["subscription_id"] is None and r["invoice_id"] is None for r in records)
    assert result.count == 2


def test_duplicate_month_with_no_eligible_transactions_returns_zero():
    """Cenário 4 — mês de origem sem transações elegíveis retorna count=0, nada é criado."""
    service, mock_repo, _ = _make_service()
    mock_repo.find_default_by_month.return_value = []

    payload = DuplicateMonthDTO(source_month=1, source_year=2026, target_month=2, target_year=2026)
    result = service.duplicate_month(user_id=1, account_id=1, data=payload)

    assert result.count == 0
    mock_repo.bulk_create.assert_not_called()


def test_duplicate_month_appends_without_overwriting_existing_target_month():
    """Cenário 5 — duplicar mês nunca lê, edita ou remove lançamentos do mês de destino."""
    service, mock_repo, _ = _make_service()
    t1 = _make_original_transaction(title="Internet", amount=15000, due_date=date(2026, 7, 20))
    mock_repo.find_default_by_month.return_value = [t1]
    mock_repo.bulk_create.return_value = [MagicMock()]

    payload = DuplicateMonthDTO(source_month=7, source_year=2026, target_month=8, target_year=2026)
    service.duplicate_month(user_id=1, account_id=1, data=payload)

    mock_repo.soft_delete.assert_not_called()
    mock_repo.bulk_soft_delete.assert_not_called()
    mock_repo.update.assert_not_called()
    mock_repo.bulk_create.assert_called_once()


def test_duplicate_month_recalculates_due_date_for_shorter_target_month():
    """Requisito funcional 8 da Spec — dia 31 em mês de origem ajusta para o último dia do destino."""
    service, mock_repo, _ = _make_service()
    t1 = _make_original_transaction(title="Conta", amount=10000, due_date=date(2026, 1, 31))
    mock_repo.find_default_by_month.return_value = [t1]
    mock_repo.bulk_create.return_value = [MagicMock()]

    payload = DuplicateMonthDTO(source_month=1, source_year=2026, target_month=2, target_year=2026)
    service.duplicate_month(user_id=1, account_id=1, data=payload)

    records = mock_repo.bulk_create.call_args[0][0]
    assert records[0]["due_date"] == date(2026, 2, 28)  # 2026 não é bissexto
