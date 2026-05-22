"""Tests for dex_studio.config module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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


class TestStudioPrefs:
    def test_defaults(self) -> None:
        prefs = StudioPrefs()
        assert prefs.theme == "dark"
        assert prefs.port == 7860
        assert prefs.host == "127.0.0.1"
        assert prefs.native_mode is True

    def test_immutable(self) -> None:
        prefs = StudioPrefs()
        with pytest.raises((AttributeError, TypeError)):
            prefs.theme = "light"  # type: ignore[misc]

    def test_custom_values(self) -> None:
        prefs = StudioPrefs(theme="light", port=8080)
        assert prefs.theme == "light"
        assert prefs.port == 8080


class TestProjectEntry:
    def test_fields(self, tmp_path: Path) -> None:
        cfg = tmp_path / "dex.yaml"
        cfg.touch()
        entry = ProjectEntry(name="moviedex", config_path=cfg)
        assert entry.name == "moviedex"
        assert entry.config_path == cfg

    def test_immutable(self, tmp_path: Path) -> None:
        cfg = tmp_path / "dex.yaml"
        entry = ProjectEntry(name="x", config_path=cfg)
        with pytest.raises((AttributeError, TypeError)):
            entry.name = "y"  # type: ignore[misc]


class TestPrefsRoundtrip:
    def test_save_and_load(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        prefs_file = tmp_path / "prefs.yaml"
        monkeypatch.setattr("dex_studio.config._PREFS_FILE", prefs_file)
        monkeypatch.setattr("dex_studio.config._STUDIO_DIR", tmp_path)

        save_prefs(StudioPrefs(theme="light", port=9000))
        loaded = load_prefs()
        assert loaded.theme == "light"
        assert loaded.port == 9000

    def test_load_missing_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("dex_studio.config._PREFS_FILE", tmp_path / "missing.yaml")
        prefs = load_prefs()
        assert isinstance(prefs, StudioPrefs)
        assert prefs.theme == "dark"

    def test_load_ignores_unknown_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefs_file = tmp_path / "prefs.yaml"
        prefs_file.write_text("theme: light\nunknown_key: 99\n")
        monkeypatch.setattr("dex_studio.config._PREFS_FILE", prefs_file)
        prefs = load_prefs()
        assert prefs.theme == "light"


class TestProjectsRoundtrip:
    def test_save_and_load(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        projects_file = tmp_path / "projects.yaml"
        monkeypatch.setattr("dex_studio.config._PROJECTS_FILE", projects_file)
        monkeypatch.setattr("dex_studio.config._STUDIO_DIR", tmp_path)

        cfg = tmp_path / "dex.yaml"
        cfg.touch()
        entries = [ProjectEntry(name="test", config_path=cfg)]
        save_projects(entries)

        data = yaml.safe_load(projects_file.read_text())
        assert "test" in data["projects"]

        loaded = load_projects()
        assert len(loaded) == 1
        assert loaded[0].name == "test"

    def test_add_and_remove(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        projects_file = tmp_path / "projects.yaml"
        monkeypatch.setattr("dex_studio.config._PROJECTS_FILE", projects_file)
        monkeypatch.setattr("dex_studio.config._STUDIO_DIR", tmp_path)

        cfg = tmp_path / "dex.yaml"
        cfg.touch()

        add_project("alpha", cfg)
        projects = load_projects()
        names = [p.name for p in projects]
        assert "alpha" in names

        remove_project("alpha")
        projects = load_projects()
        names = [p.name for p in projects]
        assert "alpha" not in names

    def test_add_replaces_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        projects_file = tmp_path / "projects.yaml"
        monkeypatch.setattr("dex_studio.config._PROJECTS_FILE", projects_file)
        monkeypatch.setattr("dex_studio.config._STUDIO_DIR", tmp_path)

        cfg1 = tmp_path / "dex1.yaml"
        cfg2 = tmp_path / "dex2.yaml"
        cfg1.touch()
        cfg2.touch()

        add_project("proj", cfg1)
        add_project("proj", cfg2)
        projects = load_projects()
        matches = [p for p in projects if p.name == "proj"]
        assert len(matches) == 1
        assert matches[0].config_path == cfg2.resolve()
