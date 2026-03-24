"""Tests for dex_studio.config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from dex_studio.config import ProjectEntry, StudioConfig, load_config


class TestStudioConfig:
    def test_defaults(self) -> None:
        config = StudioConfig()
        assert config.api_url == "http://localhost:17000"
        assert config.theme == "dark"
        assert config.port == 7860

    def test_custom_values(self) -> None:
        config = StudioConfig(api_url="http://prod:17000", theme="light")
        assert config.api_url == "http://prod:17000"

    def test_immutable(self) -> None:
        config = StudioConfig()
        with pytest.raises(AttributeError):
            config.api_url = "http://other"  # type: ignore[misc]


class TestProjectEntry:
    def test_project_entry(self) -> None:
        entry = ProjectEntry(
            name="movie-analytics",
            url="http://localhost:17000",
            icon="movie",
        )
        assert entry.name == "movie-analytics"
        assert entry.token is None


class TestLoadConfig:
    def test_loads_from_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("api_url: http://custom:17000\ntheme: light\n")
        config = load_config(path=cfg_file)
        assert config.api_url == "http://custom:17000"
        assert config.theme == "light"

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_URL", "http://env:9999")
        config = load_config()
        assert config.api_url == "http://env:9999"

    def test_missing_file_returns_defaults(self) -> None:
        config = load_config(path=Path("/nonexistent/config.yaml"))
        assert config.api_url == "http://localhost:17000"
