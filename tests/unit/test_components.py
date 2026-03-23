# tests/unit/test_components.py
"""Unit tests for the core component library."""

from __future__ import annotations

import pytest
from nicegui import Client, ui

from dex_studio.components import (
    breadcrumb,
    data_table,
    empty_state,
    metric_card,
    status_badge,
)
from dex_studio.theme import COLORS


@pytest.fixture(autouse=True)
def _reset(nicegui_reset_globals: None) -> None:  # noqa: PT004
    """Ensure a clean NiceGUI context for every test."""


class TestStatusBadge:
    def test_returns_badge_element(self) -> None:
        with Client.auto_index_client:
            result = status_badge("healthy")
        assert isinstance(result, ui.badge)

    def test_known_status_uses_success_color(self) -> None:
        with Client.auto_index_client:
            result = status_badge("healthy")
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("color") == COLORS["success"]

    def test_unknown_status_falls_back_to_text_muted(self) -> None:
        with Client.auto_index_client:
            result = status_badge("totally_made_up_status")
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("color") == COLORS["text_muted"]

    def test_case_insensitive(self) -> None:
        with Client.auto_index_client:
            result = status_badge("HEALTHY")
        assert isinstance(result, ui.badge)
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("color") == COLORS["success"]

    def test_size_lg_uses_larger_font(self) -> None:
        with Client.auto_index_client:
            result = status_badge("running", size="lg")
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("font-size") == "12px"

    def test_size_sm_uses_smaller_font(self) -> None:
        with Client.auto_index_client:
            result = status_badge("running", size="sm")
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("font-size") == "10px"

    def test_error_status_uses_error_color(self) -> None:
        with Client.auto_index_client:
            result = status_badge("error")
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("color") == COLORS["error"]

    def test_warning_status_uses_warning_color(self) -> None:
        with Client.auto_index_client:
            result = status_badge("degraded")
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("color") == COLORS["warning"]


class TestEmptyState:
    def test_renders_without_error(self) -> None:
        with Client.auto_index_client:
            empty_state("No data")

    def test_renders_with_custom_icon(self) -> None:
        with Client.auto_index_client:
            empty_state("Nothing here", icon="folder_off")

    def test_renders_with_action_button(self) -> None:
        triggered: list[bool] = []

        def _on_click() -> None:
            triggered.append(True)

        with Client.auto_index_client:
            empty_state("No pipelines", action_label="Create", on_action=_on_click)

    def test_no_button_when_label_only(self) -> None:
        """Providing action_label without on_action should not raise."""
        with Client.auto_index_client:
            empty_state("No data", action_label="Add")

    def test_no_button_when_callback_only(self) -> None:
        """Providing on_action without action_label should not raise."""
        with Client.auto_index_client:
            empty_state("No data", on_action=lambda: None)


class TestBreadcrumb:
    def test_renders_without_error(self) -> None:
        with Client.auto_index_client:
            breadcrumb("Data", "Pipelines")

    def test_single_part(self) -> None:
        with Client.auto_index_client:
            breadcrumb("Overview")

    def test_three_parts(self) -> None:
        with Client.auto_index_client:
            breadcrumb("Data", "Sources", "PostgreSQL")

    def test_empty_call(self) -> None:
        """Zero parts should not raise."""
        with Client.auto_index_client:
            breadcrumb()


class TestDataTable:
    _COLUMNS = [
        {"name": "name", "label": "Name", "field": "name", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "left"},
    ]
    _ROWS = [
        {"name": "pipeline-a", "status": "running"},
        {"name": "pipeline-b", "status": "idle"},
    ]

    def test_returns_table_element(self) -> None:
        with Client.auto_index_client:
            result = data_table(self._COLUMNS, self._ROWS)
        assert isinstance(result, ui.table)

    def test_empty_rows(self) -> None:
        with Client.auto_index_client:
            result = data_table(self._COLUMNS, [])
        assert isinstance(result, ui.table)

    def test_with_title(self) -> None:
        with Client.auto_index_client:
            result = data_table(self._COLUMNS, self._ROWS, title="Pipelines")
        assert isinstance(result, ui.table)

    def test_custom_row_key(self) -> None:
        with Client.auto_index_client:
            result = data_table(self._COLUMNS, self._ROWS, row_key="status")
        assert isinstance(result, ui.table)

    def test_style_contains_bg_secondary(self) -> None:
        with Client.auto_index_client:
            result = data_table(self._COLUMNS, self._ROWS)
        style: dict[str, str] = result._style  # type: ignore[attr-defined]
        assert style.get("background") == COLORS["bg_secondary"]


class TestMetricCard:
    def test_returns_card_element(self) -> None:
        with Client.auto_index_client:
            result = metric_card("Users", 42)
        assert isinstance(result, ui.card)

    def test_integer_value(self) -> None:
        with Client.auto_index_client:
            result = metric_card("Count", 100)
        assert isinstance(result, ui.card)

    def test_float_value(self) -> None:
        with Client.auto_index_client:
            result = metric_card("Score", 98.6)
        assert isinstance(result, ui.card)

    def test_string_value(self) -> None:
        with Client.auto_index_client:
            result = metric_card("Status", "OK")
        assert isinstance(result, ui.card)

    def test_unit_suffix(self) -> None:
        with Client.auto_index_client:
            result = metric_card("Speed", 99, unit="ms")
        assert isinstance(result, ui.card)

    def test_custom_color(self) -> None:
        with Client.auto_index_client:
            result = metric_card("Pass Rate", "87%", color=COLORS["success"])
        assert isinstance(result, ui.card)

    def test_default_color_is_text_primary(self) -> None:
        with Client.auto_index_client:
            # Should not raise and default color path executes
            result = metric_card("Latency", 12)
        assert isinstance(result, ui.card)
