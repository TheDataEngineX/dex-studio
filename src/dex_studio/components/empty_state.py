# src/dex_studio/components/empty_state.py
"""Empty state — placeholder shown when a list/section has no data."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["empty_state"]


def empty_state(
    message: str,
    *,
    icon: str = "inbox",
    action_label: str | None = None,
    on_action: Callable[[], None] | None = None,
) -> None:
    """Render a centred empty-state placeholder.

    Args:
        message: Primary message text.
        icon: Material icon name.
        action_label: Optional button label.
        on_action: Optional callback for the action button.
    """
    with ui.column().classes("items-center justify-center w-full py-12 gap-3"):
        ui.icon(icon, size="xl").style(f"color: {COLORS['text_dim']}")
        ui.label(message).style(
            f"color: {COLORS['text_muted']}; font-size: 14px; text-align: center;"
        )
        if action_label and on_action:
            ui.button(action_label, on_click=on_action).props("flat").style(
                f"color: {COLORS['accent']}"
            )
