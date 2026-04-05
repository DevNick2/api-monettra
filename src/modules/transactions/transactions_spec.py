"""
Testes unitários — TransactionsService
Cobertura:
  - v0.8: _resolve_paid_status_for_manual_date (helper puro)
  - v0.8: create() aplica regra de data automaticamente
  - v0.8: update() recalcula is_paid ao trocar data
  - v0.9: get_summary() retorna e cacheia TransactionSummaryResponse
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.modules.transactions.transactions_service import (
    TransactionsService,
    _resolve_paid_status_for_manual_date,
)
from src.modules.transactions.dtos import (
    CreateTransactionDTO,
    UpdateTransactionDTO,
    TransactionSummaryResponse,
)


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
