"""Metric card component — large number with label and optional trend."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["metric_card"]


def metric_card(
    label: str,
    value: str | int | float,
    *,
    unit: str = "",
    icon: str | None = None,
    color: str | None = None,
) -> ui.card:
    """Render a card displaying a single metric prominently.

    Parameters
    ----------
    label:
        Metric name (shown below the value).
    value:
        The metric value to display.
    unit:
        Optional unit suffix (e.g. ``%``, ``ms``).
    icon:
        Optional Material icon.
    color:
        Override colour for the value text.
    """
    value_color = color or COLORS["text_primary"]

    with ui.card().classes("dex-card") as card:
        if icon:
            ui.icon(icon, size="xs").style(f"color: {COLORS['accent']}")
        ui.label(f"{value}{unit}").classes("metric-value").style(f"color: {value_color}")
        ui.label(label).classes("metric-label")
    return card
