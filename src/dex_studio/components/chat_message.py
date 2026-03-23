"""Chat message bubble — user or agent with tool call rendering."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["chat_message"]


def chat_message(
    role: str,
    content: str,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    """Render a chat message bubble."""
    is_user = role == "user"
    avatar_bg = COLORS["border"] if is_user else COLORS["accent"]
    avatar_text = "U" if is_user else "A"

    with ui.row().classes("gap-3 w-full").style("margin-bottom: 20px;"):
        ui.label(avatar_text).style(
            f"width: 28px; height: 28px; background: {avatar_bg}; border-radius: 50%; "
            f"display: flex; align-items: center; justify-content: center; font-size: 12px; "
            f"flex-shrink: 0; color: white;"
        )

        with ui.column().classes("flex-1"):
            if tool_calls:
                for tc in tool_calls:
                    from dex_studio.components.tool_call_block import tool_call_block

                    tool_call_block(
                        name=tc.get("name", "unknown"),
                        args=tc.get("args", ""),
                        duration=tc.get("duration"),
                        status=tc.get("status", "done"),
                    )

            ui.label(content).style(
                f"background: {COLORS['bg_secondary']}; padding: 12px 16px; "
                f"border-radius: 12px; border-top-left-radius: {'12px' if is_user else '4px'}; "
                f"max-width: 80%;"
            )
