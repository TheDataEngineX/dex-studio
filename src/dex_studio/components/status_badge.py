# src/dex_studio/components/status_badge.py
"""Status badge — inline pill showing a component/pipeline status."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["status_badge"]

_STATUS_COLORS: dict[str, str] = {
    "healthy": COLORS["success"],
    "alive": COLORS["success"],
    "ready": COLORS["success"],
    "running": COLORS["success"],
    "completed": COLORS["success"],
    "degraded": COLORS["warning"],
    "starting": COLORS["warning"],
    "pending": COLORS["warning"],
    "unhealthy": COLORS["error"],
    "failed": COLORS["error"],
    "error": COLORS["error"],
    "unavailable": COLORS["text_dim"],
    "none_configured": COLORS["text_dim"],
    "unknown": COLORS["text_muted"],
}


def status_badge(status: str, *, size: str = "sm") -> ui.badge:
    """Render a coloured status pill.

    Args:
        status: Status string (matched case-insensitively).
        size: Badge size — ``sm`` (default) or ``lg``.
    """
    color = _STATUS_COLORS.get(status.lower(), COLORS["text_muted"])
    font = "10px" if size == "sm" else "12px"
    badge = ui.badge(status.upper()).style(
        f"background: {color}22; color: {color}; "
        f"font-size: {font}; font-weight: 600; "
        f"padding: 2px 10px; border-radius: 12px;"
    )
    return badge
