"""Tests for dex_studio.cli module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dex_studio.cli import _build_parser, main


class TestCLIParser:
    def test_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.host == "0.0.0.0"
        assert args.port == 7860
        assert args.reload is False
        assert args.version is False

    def test_host_arg(self) -> None:
        args = _build_parser().parse_args(["--host", "127.0.0.1"])
        assert args.host == "127.0.0.1"

    def test_port_arg(self) -> None:
        args = _build_parser().parse_args(["--port", "8080"])
        assert args.port == 8080

    def test_reload_flag(self) -> None:
        args = _build_parser().parse_args(["--reload"])
        assert args.reload is True

    def test_version_flag(self) -> None:
        args = _build_parser().parse_args(["--version"])
        assert args.version is True

    def test_invalid_port_type(self) -> None:
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["--port", "notanumber"])


class TestMain:
    def test_version_prints_and_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "dex-studio" in out

    def test_starts_uvicorn_with_defaults(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main([])
        mock_uvicorn.run.assert_called_once()
        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs["host"] == "0.0.0.0"
        assert call_kwargs.kwargs["port"] == 7860
        assert call_kwargs.kwargs["reload"] is False

    def test_starts_uvicorn_with_custom_port(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["--port", "9000", "--host", "127.0.0.1"])
        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs["port"] == 9000
        assert call_kwargs.kwargs["host"] == "127.0.0.1"

    def test_starts_uvicorn_with_reload(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["--reload"])
        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs["reload"] is True
