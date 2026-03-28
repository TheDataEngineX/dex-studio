"""AI Agents page — agent selector, chat interface, and inspector panel.

Route: ``/ai/agents``

Uses DexEngine directly for agent access:
    engine.config.ai.agents  -> agent config dict
    engine.agents             -> live agent instances
    engine.agents[name].run() -> agent response
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.chat_message import chat_message
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.components.inspector_panel import inspector_panel
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


def _render_chat_area(
    engine: DexEngine,
    agent_names: list[str],
) -> None:
    """Render the left chat area with agent selector, messages, and input bar."""
    with (
        ui.column()
        .classes("flex-1")
        .style(
            f"background: {COLORS['bg_primary']}; "
            "display: flex; flex-direction: column;"
            " height: calc(100vh - 88px);"
        )
    ):
        # Agent selector bar
        with (
            ui.row()
            .classes("items-center gap-3 w-full")
            .style(
                f"padding: 12px 16px; border-bottom: 1px solid"
                f" {COLORS['border']}; "
                f"background: {COLORS['bg_secondary']};"
            )
        ):
            ui.label("Agent:").style(f"font-size: 13px; color: {COLORS['text_muted']};")
            selected_agent: ui.select = (
                ui.select(
                    options=agent_names,
                    value=agent_names[0] if agent_names else None,
                )
                .style("min-width: 200px;")
                .props("outlined dense dark")
            )

        # Messages container
        messages_col = (
            ui.column()
            .classes("flex-1 w-full")
            .style("overflow-y: auto; padding: 16px; gap: 0; flex-grow: 1; min-height: 0;")
        )

        if not agent_names:
            with messages_col:
                empty_state("No agents configured", icon="smart_toy")

        # Input bar
        with (
            ui.row()
            .classes("items-end gap-3 w-full")
            .style(
                f"padding: 12px 16px; border-top: 1px solid"
                f" {COLORS['border']}; "
                f"background: {COLORS['bg_secondary']};"
            )
        ):
            message_input = (
                ui.textarea(placeholder="Type a message...")
                .classes("flex-1")
                .props("outlined dense dark rows=2")
            )

            async def send_message() -> None:
                msg = message_input.value.strip()
                if not msg:
                    return
                agent_name = selected_agent.value
                if not agent_name:
                    return

                message_input.value = ""

                with messages_col:
                    chat_message("user", msg)

                # Check if agent is available (LLM up)
                if agent_name not in engine.agents:
                    response_text = (
                        "LLM provider unavailable.\n\n"
                        "To enable AI agents, start Ollama:\n"
                        "  ollama serve\n"
                        "  ollama pull qwen3:8b\n\n"
                        "Then restart DEX Studio."
                    )
                    with messages_col:
                        chat_message("agent", response_text)
                    return

                try:
                    result = await asyncio.to_thread(engine.agents[agent_name].run, msg)
                    response_text = result.response if hasattr(result, "response") else str(result)
                    tool_calls: int = result.tool_calls if hasattr(result, "tool_calls") else 0
                except Exception as exc:
                    response_text = f"[Error: {exc}]"
                    tool_calls = 0

                with messages_col:
                    chat_message(
                        "agent",
                        response_text,
                        tool_calls=tool_calls,
                    )

            ui.button(
                "Send",
                icon="send",
                on_click=send_message,
            ).props("color=indigo").style("height: 40px;")


def _render_inspector(
    engine: DexEngine,
    agent_names: list[str],
) -> None:
    """Render the right inspector panel for the first agent."""
    with inspector_panel("Agent Inspector", width=320) as panel_content, panel_content:
        if not agent_names:
            ui.label("No agents available.").style(
                f"padding: 12px 16px; font-size: 12px; color: {COLORS['text_dim']};"
            )
            return

        first_name = agent_names[0]
        agent_cfg = engine.config.ai.agents.get(first_name)
        _render_agent_inspector(first_name, agent_cfg)


@ui.page("/ai/agents")
async def ai_agents_page() -> None:
    """Render the AI agents chat interface with inspector panel."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai/agents")

        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Agent Chat")

            if engine is None:
                with ui.column().classes("p-6 gap-4 w-full"):
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                return

            agent_names = list(engine.config.ai.agents.keys())

            with ui.row().classes("flex-1 w-full").style("gap: 0; overflow: hidden;"):
                _render_chat_area(engine, agent_names)
                _render_inspector(engine, agent_names)


def _render_agent_inspector(name: str, agent_cfg: Any) -> None:
    """Render agent metadata in the inspector panel."""
    if agent_cfg is None:
        ui.label("Select an agent to inspect.").style(
            f"padding: 12px 16px; font-size: 12px; color: {COLORS['text_dim']};"
        )
        return

    with ui.column().classes("w-full gap-2").style("padding: 12px 16px;"):
        ui.label(name).style(f"font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};")

        # Show system prompt snippet instead of description
        if agent_cfg.system_prompt:
            snippet = agent_cfg.system_prompt[:120]
            if len(agent_cfg.system_prompt) > 120:
                snippet += "..."
            ui.label(snippet).style(
                f"font-size: 12px; color: {COLORS['text_muted']}; margin-top: 4px;"
            )

        ui.element("div").style(
            f"width: 100%; height: 1px; background: {COLORS['divider']}; margin: 8px 0;"
        )

        with ui.row().classes("items-center gap-2"):
            ui.label("Runtime").style(
                f"font-size: 10px; text-transform: uppercase; "
                f"color: {COLORS['text_faint']};"
                " letter-spacing: 0.05em;"
            )
            ui.label(str(agent_cfg.runtime)).style(
                f"font-size: 12px; color: {COLORS['text_muted']};"
            )

        if agent_cfg.tools:
            ui.label("Tools").style(
                f"font-size: 10px; text-transform: uppercase; "
                f"color: {COLORS['text_faint']};"
                " letter-spacing: 0.05em; margin-top: 8px;"
            )
            for tool_name in agent_cfg.tools:
                with ui.row().classes("items-center gap-2").style("margin-top: 4px;"):
                    ui.icon("build", size="xs").style(f"color: {COLORS['accent']};")
                    ui.label(str(tool_name)).style(
                        f"font-size: 12px; color: {COLORS['text_muted']};"
                    )
