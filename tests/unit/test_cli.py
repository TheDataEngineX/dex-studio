"""Tests for dex_studio.cli module."""

from __future__ import annotations

import pytest

from dex_studio.cli import _build_parser


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
