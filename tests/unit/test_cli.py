"""Tests for dex_studio.cli module."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dex_studio.cli import _build_parser, main
from dex_studio.config import ProjectEntry, StudioConfig


class TestCLIParser:
    """Tests for the CLI argument parser."""

    def test_default_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.url is None
        assert args.token is None
        assert args.config is None
        assert args.theme is None
        assert args.version is False
        assert args.project is None

    def test_url_arg(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--url", "http://custom:9000"])
        assert args.url == "http://custom:9000"

    def test_token_arg(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--token", "secret"])
        assert args.token == "secret"

    def test_theme_choices(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--theme", "light"])
        assert args.theme == "light"

        with pytest.raises(SystemExit):
            parser.parse_args(["--theme", "invalid"])

    def test_version_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--version"])
        assert args.version is True

    def test_project_flag_parses(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--project", "my-project"])
        assert args.project == "my-project"

    def test_project_default_is_none(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.project is None


class TestMainProjectFlag:
    """Tests for --project behaviour in main()."""

    def _make_start_mock(self) -> MagicMock:
        return MagicMock()

    def test_unknown_project_exits_with_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unknown project name should print to stderr and exit with code 1."""
        with (
            patch("dex_studio.cli.load_config", return_value=StudioConfig()),
            patch("dex_studio.config.load_projects", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main(["--project", "nonexistent"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "nonexistent" in captured.err
        assert "not found" in captured.err

    def test_project_url_overrides_config(self) -> None:
        """--project should set api_url from the matched ProjectEntry."""
        project = ProjectEntry(name="staging", url="http://staging:17000", token=None)

        captured_config: dict[str, Any] = {}

        def fake_start(*, config: StudioConfig) -> None:
            captured_config.update(asdict(config))

        with (
            patch("dex_studio.cli.load_config", return_value=StudioConfig()),
            patch("dex_studio.config.load_projects", return_value=[project]),
            patch("dex_studio.app.start", fake_start),
        ):
            main(["--project", "staging"])

        assert captured_config["api_url"] == "http://staging:17000"
        assert captured_config["api_token"] is None

    def test_project_token_overrides_config(self) -> None:
        """--project should set api_token when the project has one."""
        project = ProjectEntry(name="prod", url="http://prod:17000", token="tok-abc")

        captured_config: dict[str, Any] = {}

        def fake_start(*, config: StudioConfig) -> None:
            captured_config.update(asdict(config))

        with (
            patch("dex_studio.cli.load_config", return_value=StudioConfig()),
            patch("dex_studio.config.load_projects", return_value=[project]),
            patch("dex_studio.app.start", fake_start),
        ):
            main(["--project", "prod"])

        assert captured_config["api_url"] == "http://prod:17000"
        assert captured_config["api_token"] == "tok-abc"

    def test_explicit_url_overrides_project(self) -> None:
        """--url specified after --project should win (explicit beats project lookup)."""
        project = ProjectEntry(name="staging", url="http://staging:17000", token=None)

        captured_config: dict[str, Any] = {}

        def fake_start(*, config: StudioConfig) -> None:
            captured_config.update(asdict(config))

        with (
            patch("dex_studio.cli.load_config", return_value=StudioConfig()),
            patch("dex_studio.config.load_projects", return_value=[project]),
            patch("dex_studio.app.start", fake_start),
        ):
            main(["--project", "staging", "--url", "http://override:9999"])

        assert captured_config["api_url"] == "http://override:9999"
