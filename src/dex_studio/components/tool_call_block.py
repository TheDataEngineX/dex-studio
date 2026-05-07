"""Tool call block — expandable display of tool invocations in agent chat."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["tool_call_block"]


def tool_call_block(
    name: str,
    args: str = "",
    *,
    duration: float | None = None,
    status: str = "done",
) -> None:
    """Render an expandable tool call block."""
    status_icon = "✓" if status == "done" else "⏳"
    status_color = COLORS["success"] if status == "done" else COLORS["warning"]
    duration_text = f"{duration:.1f}s" if duration else ""

    with (  # noqa: SIM117
        ui.expansion()
        .classes("w-full")
        .style(
            f"background: {COLORS['bg_hover']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 8px; margin-bottom: 8px;"
        )
    ):
        with ui.row().classes("items-center gap-2").style("font-size: 12px;"):
            ui.label("⚡").style(f"color: {COLORS['accent']};")
            ui.label(name).style(f"color: {COLORS['accent_light']}; font-family: monospace;")
            if args:
                ui.label("→").style(f"color: {COLORS['text_faint']};")
                ui.label(args).style(
                    f"color: {COLORS['text_dim']}; font-family: monospace; font-size: 11px; "
                    f"overflow: hidden; text-overflow: ellipsis; max-width: 300px;"
                )
            if duration_text:
                ui.label(f"{status_icon} {duration_text}").style(
                    f"margin-left: auto; color: {status_color}; font-size: 10px;"
                )
