"""
Testes unitários do CategoriesService.
"""

import pytest
from unittest.mock import MagicMock

from src.modules.categories.categories_service import CategoriesService
from src.modules.categories.dtos import CreateCategoryDTO, UpdateCategoryDTO


def _make_service(mock_repo=None, mock_user_repo=None):
    mock_repo = mock_repo or MagicMock()
    mock_user_repo = mock_user_repo or MagicMock()
    mock_user_repo.find_by_code.return_value = MagicMock(id=1)
    return CategoriesService(repository=mock_repo, user_repository=mock_user_repo)


def test_find_all_returns_list():
    mock_repo = MagicMock()
    mock_repo.find_all_by_user.return_value = []
    service = _make_service(mock_repo=mock_repo)
    result = service.find_all("some-user-code")
    assert result == []
    mock_repo.find_all_by_user.assert_called_once_with(1)


def test_create_calls_repository():
    mock_repo = MagicMock()
    created = MagicMock()
    mock_repo.create.return_value = created
    service = _make_service(mock_repo=mock_repo)

    dto = CreateCategoryDTO(title="Alimentação", color="#8b6914", icon_name="utensils")
    result = service.create("some-user-code", dto)

    mock_repo.create.assert_called_once()
    assert result == created


def test_remove_calls_soft_delete():
    from uuid import uuid4
    mock_repo = MagicMock()
    category = MagicMock()
    mock_repo.find_by_code.return_value = category
    service = _make_service(mock_repo=mock_repo)

    service.remove("some-user-code", uuid4())
    mock_repo.soft_delete.assert_called_once_with(category)


def test_remove_raises_if_not_found():
    from uuid import uuid4
    from fastapi import HTTPException
    mock_repo = MagicMock()
    mock_repo.find_by_code.return_value = None
    service = _make_service(mock_repo=mock_repo)

    with pytest.raises(HTTPException) as exc_info:
        service.remove("some-user-code", uuid4())
    assert exc_info.value.status_code == 404


def test_update_raises_if_not_found():
    from uuid import uuid4
    from fastapi import HTTPException
    mock_repo = MagicMock()
    mock_repo.find_by_code.return_value = None
    service = _make_service(mock_repo=mock_repo)

    with pytest.raises(HTTPException) as exc_info:
        service.update("some-user-code", uuid4(), UpdateCategoryDTO(title="Novo"))
    assert exc_info.value.status_code == 404
