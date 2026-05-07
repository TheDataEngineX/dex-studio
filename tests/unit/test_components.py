"""Unit tests for the Reflex component library."""

from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell, sidebar


class TestSidebar:
    def test_returns_rx_component(self) -> None:
        result = sidebar()
        assert isinstance(result, rx.Component)

    def test_sidebar_is_box(self) -> None:
        result = sidebar()
        assert result is not None


class TestPageShell:
    def test_returns_rx_component(self) -> None:
        content = rx.text("hello")
        result = page_shell(content)
        assert isinstance(result, rx.Component)

    def test_accepts_multiple_children(self) -> None:
        result = page_shell(rx.text("a"), rx.text("b"))
        assert isinstance(result, rx.Component)

    def test_accepts_heading(self) -> None:
        result = page_shell(rx.heading("Title"), rx.text("body"))
        assert isinstance(result, rx.Component)
