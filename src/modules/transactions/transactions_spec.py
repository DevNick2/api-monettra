"""
Testes unitários do TransactionsService.
"""

import pytest
from unittest.mock import MagicMock
from datetime import date

from src.modules.transactions.transactions_service import TransactionsService
from src.modules.transactions.dtos import CreateTransactionDTO, UpdateTransactionDTO
from src.schemas.transactions import TransactionType


def _make_service(mock_repo=None, mock_user_repo=None):
    mock_repo = mock_repo or MagicMock()
    mock_user_repo = mock_user_repo or MagicMock()
    mock_user_repo.find_by_code.return_value = MagicMock(id=1)
    return TransactionsService(repository=mock_repo, user_repository=mock_user_repo)


def test_find_all_returns_list():
    mock_repo = MagicMock()
    mock_repo.find_all_by_user.return_value = []
    service = _make_service(mock_repo=mock_repo)
    result = service.find_all("some-user-code")
    assert result == []
    mock_repo.find_all_by_user.assert_called_once_with(1)


def test_create_raises_on_negative_amount():
    from fastapi import HTTPException
    service = _make_service()
    dto = CreateTransactionDTO(
        title="Test",
        amount=-10.0,
        type=TransactionType.EXPENSE,
        due_date=date.today()
    )
    with pytest.raises(HTTPException) as exc_info:
        service.create("some-user-code", dto)
    assert exc_info.value.status_code == 422


def test_mark_as_paid_sets_is_paid():
    from uuid import uuid4
    mock_repo = MagicMock()
    transaction = MagicMock()
    transaction.is_paid = False
    transaction.paid_at = None
    mock_repo.find_by_code.return_value = transaction
    mock_repo.update.return_value = transaction

    service = _make_service(mock_repo=mock_repo)
    service.mark_as_paid("some-user-code", uuid4())

    assert transaction.is_paid is True
    assert transaction.paid_at is not None


def test_remove_calls_soft_delete():
    from uuid import uuid4
    mock_repo = MagicMock()
    transaction = MagicMock()
    mock_repo.find_by_code.return_value = transaction

    service = _make_service(mock_repo=mock_repo)
    service.remove("some-user-code", uuid4())

    mock_repo.soft_delete.assert_called_once_with(transaction)


def test_find_all_raises_if_user_not_found():
    from fastapi import HTTPException
    mock_repo = MagicMock()
    mock_user_repo = MagicMock()
    mock_user_repo.find_by_code.return_value = None
    service = TransactionsService(repository=mock_repo, user_repository=mock_user_repo)

    with pytest.raises(HTTPException) as exc_info:
        service.find_all("invalid-code")
    assert exc_info.value.status_code == 404
