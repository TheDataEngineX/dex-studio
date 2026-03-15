"""Status card component — shows a health/status indicator with label."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["status_card"]

_STATUS_COLORS = {
    "healthy": COLORS["success"],
    "alive": COLORS["success"],
    "ready": COLORS["success"],
    "started": COLORS["success"],
    "degraded": COLORS["warning"],
    "starting": COLORS["warning"],
    "unhealthy": COLORS["error"],
    "not_ready": COLORS["error"],
    "error": COLORS["error"],
    "unknown": COLORS["text_muted"],
}


def status_card(
    title: str,
    status: str,
    *,
    subtitle: str | None = None,
    icon: str = "circle",
) -> ui.card:
    """Render a card with a coloured status indicator.

    Parameters
    ----------
    title:
        Card heading.
    status:
        Status string (``healthy``, ``degraded``, ``unhealthy``, etc.).
    subtitle:
        Optional secondary text.
    icon:
        Material icon name.
    """
    color = _STATUS_COLORS.get(status.lower(), COLORS["text_muted"])

    with ui.card().classes("dex-card") as card:
        with ui.row().classes("items-center gap-3 no-wrap"):
            ui.icon(icon, size="sm").style(f"color: {color}")
            with ui.column().classes("gap-0"):
                ui.label(title).classes("font-semibold text-sm").style(
                    f"color: {COLORS['text_primary']}"
                )
                if subtitle:
                    ui.label(subtitle).classes("text-xs").style(
                        f"color: {COLORS['text_secondary']}"
                    )
        with ui.row().classes("items-center gap-2 mt-2"):
            ui.icon("circle", size="2xs").style(f"color: {color}")
            ui.label(status.upper()).classes("text-xs font-mono font-bold").style(f"color: {color}")
    return card
