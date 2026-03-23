# src/dex_studio/components/metric_card.py
"""Metric card — large KPI display with label and optional trend."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["metric_card"]


def metric_card(
    label: str,
    value: str | int | float,
    *,
    unit: str = "",
    color: str | None = None,
) -> ui.card:
    """Render a metric card with large value and label."""
    value_color = color or COLORS["text_primary"]
    card = ui.card().classes("dex-card").style("padding: 16px; min-width: 140px;")
    with card:
        ui.label(label.upper()).classes("section-title")
        display = f"{value}{unit}" if unit else str(value)
        ui.label(display).style(
            f"font-size: 28px; font-weight: 700; color: {value_color}; margin-top: 4px;"
        )
    return card
