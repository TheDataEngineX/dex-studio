"""Tests for dex_studio.config module — DB-backed prefs and project registry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dex_studio.config import (
    ProjectEntry,
    StudioPrefs,
    add_project,
    load_prefs,
    load_projects,
    remove_project,
    save_prefs,
    save_projects,
)


def _mock_db(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: dict[str, str] | None = None,
    projects: list[tuple[str, str]] | None = None,
) -> MagicMock:
    """Patch all db_store functions; return a mock so tests can assert on calls."""
    s = settings or {}
    p = projects or []
    store = MagicMock()
    store.get_setting.side_effect = lambda k: s.get(k)
    store.set_setting.side_effect = lambda k, v: s.__setitem__(k, v)
    store.delete_setting.side_effect = lambda k: s.pop(k, None)
    store.get_projects.return_value = list(p)
    monkeypatch.setattr("dex_studio.db_store.get_setting", store.get_setting)
    monkeypatch.setattr("dex_studio.db_store.set_setting", store.set_setting)
    monkeypatch.setattr("dex_studio.db_store.delete_setting", store.delete_setting)
    monkeypatch.setattr("dex_studio.db_store.get_projects", store.get_projects)
    monkeypatch.setattr("dex_studio.db_store.set_project", store.set_project)
    monkeypatch.setattr("dex_studio.db_store.delete_project", store.delete_project)
    return store


class TestStudioPrefsDefaults:
    def test_default_port(self) -> None:
        assert StudioPrefs().port == 7860

    def test_default_host(self) -> None:
        assert StudioPrefs().host == "127.0.0.1"

    def test_default_budget(self) -> None:
        assert StudioPrefs().monthly_budget_usd == 25.0

    def test_default_config_path_empty(self) -> None:
        assert StudioPrefs().default_config_path == ""


class TestPrefsRoundtrip:
    def test_defaults_when_db_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_db(monkeypatch)
        prefs = load_prefs()
        assert prefs.monthly_budget_usd == 25.0
        assert prefs.default_config_path == ""

    def test_save_and_load_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_db(monkeypatch)
        save_prefs(StudioPrefs(monthly_budget_usd=99.5))
        loaded = load_prefs()
        assert loaded.monthly_budget_usd == 99.5

    def test_save_and_load_default_config_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_db(monkeypatch)
        save_prefs(StudioPrefs(default_config_path="/some/path/dex.yaml"))
        loaded = load_prefs()
        assert loaded.default_config_path == "/some/path/dex.yaml"

    def test_ui_only_fields_not_persisted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _mock_db(monkeypatch)
        save_prefs(StudioPrefs(window_width=2560, window_height=1440, native_mode=False))
        keys_written = [call[0][0] for call in store.set_setting.call_args_list]
        assert "pref.monthly_budget_usd" in keys_written
        assert "pref.default_config_path" in keys_written
        assert not any("window" in k or "native" in k for k in keys_written)

    def test_invalid_budget_in_db_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_db(monkeypatch, settings={"pref.monthly_budget_usd": "not-a-number"})
        prefs = load_prefs()
        assert prefs.monthly_budget_usd == 25.0


class TestProjectRegistry:
    def test_load_from_db(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "dex.yaml"
        cfg.touch()
        _mock_db(monkeypatch, projects=[("myproject", str(cfg))])
        projects = load_projects()
        assert len(projects) == 1
        assert projects[0].name == "myproject"
        assert projects[0].config_path == cfg.resolve()

    def test_empty_db_returns_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_db(monkeypatch, projects=[])
        monkeypatch.setattr(
            "dex_studio.config._default_projects",
            lambda: [ProjectEntry(name="demo", config_path=Path("/demo/dex.yaml"))],
        )
        projects = load_projects()
        assert projects[0].name == "demo"

    def test_save_projects_upserts_new(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        store = _mock_db(monkeypatch, projects=[])
        cfg = tmp_path / "dex.yaml"
        cfg.touch()
        save_projects([ProjectEntry(name="p1", config_path=cfg)])
        store.set_project.assert_called_once_with("p1", str(cfg))

    def test_save_projects_removes_old(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg = tmp_path / "dex.yaml"
        cfg.touch()
        store = _mock_db(monkeypatch, projects=[("old", str(cfg))])
        save_projects([])
        store.delete_project.assert_called_once_with("old")

    def test_add_project(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "proj" / "dex.yaml"
        cfg.parent.mkdir()
        cfg.touch()
        store = _mock_db(monkeypatch, projects=[("proj", str(cfg))])
        add_project("proj", cfg)
        store.set_project.assert_called_once()

    def test_remove_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _mock_db(monkeypatch, projects=[])
        remove_project("gone")
        store.delete_project.assert_called_once_with("gone")
