"""Shared test fixtures for DEX Studio."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patch_db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Stub dex_studio.db_store so auth/session code never touches a real DB."""

    def _patch(*, return_hash: str | None = None) -> None:
        monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=return_hash))
        monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.delete_setting", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
        monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())

    return _patch
