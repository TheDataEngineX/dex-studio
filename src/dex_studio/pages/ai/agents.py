"""AI Agents page — agent selector, chat interface, and inspector panel.

Route: ``/ai/agents``

Drives DEX engine endpoints:
    GET  /api/v1/ai/agents              → list agents
    GET  /api/v1/ai/agents/{name}       → agent metadata
    POST /api/v1/ai/agents/{name}/chat  → send message
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.chat_message import chat_message
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.components.inspector_panel import inspector_panel
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


def _render_chat_area(
    client: DexClient,
    agent_names: list[str],
) -> None:
    """Render the left chat area with agent selector, messages, and input bar."""
    with (
        ui.column()
        .classes("flex-1")
        .style(
            f"background: {COLORS['bg_primary']}; "
            "display: flex; flex-direction: column; height: calc(100vh - 88px);"
        )
    ):
        # Agent selector bar
        with (
            ui.row()
            .classes("items-center gap-3 w-full")
            .style(
                f"padding: 12px 16px; border-bottom: 1px solid {COLORS['border']}; "
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
                f"padding: 12px 16px; border-top: 1px solid {COLORS['border']}; "
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

                try:
                    result = await client.agent_chat(agent_name, msg)
                    response_text: str = result.get("response", "")
                    tool_calls: list[dict[str, Any]] = result.get("tool_calls", [])
                except DexAPIError as exc:
                    response_text = f"[Error: {exc}]"
                    tool_calls = []

                with messages_col:
                    chat_message(
                        "agent",
                        response_text,
                        tool_calls=tool_calls if tool_calls else None,
                    )

            ui.button(
                "Send",
                icon="send",
                on_click=send_message,
            ).props("color=indigo").style("height: 40px;")


def _render_inspector(
    agents: list[dict[str, Any]],
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
        first_agent = next((a for a in agents if a.get("name") == first_name), {})
        _render_agent_inspector(first_agent)


@ui.page("/ai/agents")
async def ai_agents_page() -> None:
    """Render the AI agents chat interface with inspector panel."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai/agents")

        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Agent Chat")

            if client is None:
                with ui.column().classes("p-6 gap-4 w-full"):
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                return

            agents: list[dict[str, Any]] = []
            try:
                agents_resp = await client.list_agents()
                agents = agents_resp.get("agents", [])
            except DexAPIError as exc:
                with ui.column().classes("p-6"):
                    ui.label(f"Error loading agents: {exc}").style(f"color: {COLORS['error']}")
                return

            agent_names = [a.get("name", "") for a in agents if a.get("name")]

            with ui.row().classes("flex-1 w-full").style("gap: 0; overflow: hidden;"):
                _render_chat_area(client, agent_names)
                _render_inspector(agents, agent_names)


def _render_agent_inspector(agent: dict[str, Any]) -> None:
    """Render agent metadata in the inspector panel."""
    if not agent:
        ui.label("Select an agent to inspect.").style(
            f"padding: 12px 16px; font-size: 12px; color: {COLORS['text_dim']};"
        )
        return

    with ui.column().classes("w-full gap-2").style("padding: 12px 16px;"):
        name = agent.get("name", "—")
        description = agent.get("description", "")
        runtime = agent.get("runtime", "—")
        tool_list: list[str] = agent.get("tools", [])

        ui.label(name).style(f"font-size: 14px; font-weight: 600; color: {COLORS['text_primary']};")

        if description:
            ui.label(description).style(
                f"font-size: 12px; color: {COLORS['text_muted']}; margin-top: 4px;"
            )

        ui.element("div").style(
            f"width: 100%; height: 1px; background: {COLORS['divider']}; margin: 8px 0;"
        )

        with ui.row().classes("items-center gap-2"):
            ui.label("Runtime").style(
                f"font-size: 10px; text-transform: uppercase; "
                f"color: {COLORS['text_faint']}; letter-spacing: 0.05em;"
            )
            ui.label(str(runtime)).style(f"font-size: 12px; color: {COLORS['text_muted']};")

        if tool_list:
            ui.label("Tools").style(
                f"font-size: 10px; text-transform: uppercase; "
                f"color: {COLORS['text_faint']}; letter-spacing: 0.05em; margin-top: 8px;"
            )
            for tool_name in tool_list:
                with ui.row().classes("items-center gap-2").style("margin-top: 4px;"):
                    ui.icon("build", size="xs").style(f"color: {COLORS['accent']};")
                    ui.label(str(tool_name)).style(
                        f"font-size: 12px; color: {COLORS['text_muted']};"
                    )
