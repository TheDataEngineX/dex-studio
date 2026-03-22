"""Tests for dex_studio.config module."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from dex_studio.config import StudioConfig, load_config


class TestStudioConfig:
    """Tests for the StudioConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = StudioConfig()
        assert cfg.api_url == "http://localhost:17000"
        assert cfg.api_token is None
        assert cfg.timeout == 10.0
        assert cfg.theme == "dark"
        assert cfg.window_width == 1400
        assert cfg.window_height == 900
        assert cfg.poll_interval == 5.0

    def test_custom_values(self) -> None:
        cfg = StudioConfig(
            api_url="http://dex:9000",
            api_token="tok-123",
            timeout=30.0,
            theme="light",
        )
        assert cfg.api_url == "http://dex:9000"
        assert cfg.api_token == "tok-123"
        assert cfg.timeout == 30.0
        assert cfg.theme == "light"

    def test_immutable(self) -> None:
        cfg = StudioConfig()
        with pytest.raises(AttributeError):
            cfg.api_url = "http://other"  # type: ignore[misc]


class TestLoadConfig:
    """Tests for the load_config function."""

    def test_loads_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""\
                api_url: "http://custom:8080"
                timeout: 25.0
                theme: light
            """)
        )
        cfg = load_config(path=config_file)
        assert cfg.api_url == "http://custom:8080"
        assert cfg.timeout == 25.0
        assert cfg.theme == "light"

    def test_env_overrides_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text('api_url: "http://file-url:8000"\n')

        monkeypatch.setenv("DEX_STUDIO_API_URL", "http://env-url:9000")
        cfg = load_config(path=config_file)
        assert cfg.api_url == "http://env-url:9000"

    def test_missing_file_returns_defaults(self) -> None:
        cfg = load_config(path=Path("/nonexistent/config.yaml"))
        assert cfg.api_url == "http://localhost:17000"

    def test_ignores_unknown_keys(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text('api_url: "http://ok"\nunknown_key: value\n')
        cfg = load_config(path=config_file)
        assert cfg.api_url == "http://ok"

    def test_env_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_TOKEN", "secret-token")
        cfg = load_config(path=Path("/dev/null"))
        assert cfg.api_token == "secret-token"
