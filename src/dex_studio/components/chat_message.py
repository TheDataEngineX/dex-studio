"""Chat message bubble — user or agent with tool call count."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["chat_message"]


def chat_message(
    role: str,
    content: str,
    *,
    tool_calls: int = 0,
) -> None:
    """Render a chat message bubble."""
    is_user = role == "user"
    avatar_bg = COLORS["border"] if is_user else COLORS["accent"]
    avatar_text = "U" if is_user else "A"

    with ui.row().classes("gap-3 w-full").style("margin-bottom: 20px;"):
        ui.label(avatar_text).style(
            f"width: 28px; height: 28px; background: {avatar_bg};"
            " border-radius: 50%; "
            "display: flex; align-items: center;"
            " justify-content: center; font-size: 12px; "
            "flex-shrink: 0; color: white;"
        )

        with ui.column().classes("flex-1"):
            if tool_calls > 0:
                ui.badge(
                    f"\U0001f527 {tool_calls} tool call{'s' if tool_calls != 1 else ''}"
                ).props("outline").style(f"color: {COLORS['accent_light']}; margin-bottom: 6px;")

            ui.label(content).style(
                f"background: {COLORS['bg_secondary']};"
                " padding: 12px 16px; "
                "border-radius: 12px;"
                f" border-top-left-radius:"
                f" {'12px' if is_user else '4px'}; "
                "max-width: 80%;"
            )
