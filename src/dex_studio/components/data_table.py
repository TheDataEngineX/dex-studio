# src/dex_studio/components/data_table.py
"""Data table — sortable, filterable table with row actions."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["data_table"]


def data_table(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    title: str | None = None,
    row_key: str = "name",
) -> ui.table:
    """Render a styled data table.

    Args:
        columns: List of column defs, each with 'name', 'label', 'field'.
        rows: List of row dicts.
        title: Optional table title.
        row_key: Row identifier field.
    """
    table = ui.table(
        columns=columns,
        rows=rows,
        row_key=row_key,
        title=title,
    ).classes("w-full")
    table.style(
        f"background: {COLORS['bg_secondary']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border']}; "
        f"border-radius: 8px;"
    )
    return table
