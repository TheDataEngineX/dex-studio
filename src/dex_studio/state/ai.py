"""Reflex state for all AI features — agents, chat, tools, traces, memory, workflows."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx

from dex_studio.state.base import BaseState


class AIState(BaseState):
    """State for AI pages: agent management, chat, tool registry, observability, memory."""

    agents: list[dict[str, Any]] = []
    selected_agent: str = ""
    chat_messages: list[dict[str, Any]] = []
    chat_input: str = ""
    tools: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    memory_collections: list[dict[str, Any]] = []
    workflows: list[dict[str, Any]] = []
    cost_data: list[dict[str, Any]] = []

    @rx.event
    async def load_agents(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            initialized = set(eng.agents.keys())
            cfg_agents = (eng.config.ai.agents if eng.config.ai else {}) or {}
            self.agents = [
                {
                    "name": name,
                    "type": getattr(cfg, "runtime", "builtin"),
                    "status": "available" if name in initialized else "offline",
                }
                for name, cfg in cfg_agents.items()
            ]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    def select_agent(self, name: str) -> None:
        self.selected_agent = name

    @rx.event
    def set_chat_input(self, v: str) -> None:
        self.chat_input = v

    @rx.event
    async def send_message(self) -> AsyncGenerator[None]:
        if not self.chat_input or not self.selected_agent:
            return
        user_msg = self.chat_input
        self.chat_messages = [*self.chat_messages, {"role": "user", "content": user_msg}]
        self.chat_input = ""
        self.is_loading = True
        yield
        try:
            eng = self._engine()
            agent = eng.agents.get(self.selected_agent)
            if agent is None:
                self._set_error(f"Agent '{self.selected_agent}' not found")
                return
            result = await asyncio.wait_for(agent.run(user_msg), timeout=60)
            reply = result.get("reply") or result.get("content") or str(result)
            self.chat_messages = [*self.chat_messages, {"role": "assistant", "content": reply}]
        except TimeoutError:
            self._set_error("Agent timed out")
        except Exception as exc:
            self._set_error(str(exc))
            self.chat_messages = [
                *self.chat_messages,
                {"role": "assistant", "content": f"Error: {exc}"},
            ]
        finally:
            self.is_loading = False

    @rx.event
    async def load_tools(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from dataenginex.ai.tools import tool_registry

            self.tools = [{"name": name} for name in tool_registry.list()]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_traces(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            if eng.ai_audit is not None:
                self.traces = [e.to_dict() for e in eng.ai_audit.all_events]
            else:
                self.traces = []
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_memory(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            collections = []
            if eng.ai_memory is not None:
                collections.append({"name": "short_term", "entries": len(eng.ai_memory.entries)})
            if eng.ai_long_memory is not None and hasattr(eng.ai_long_memory, "entries"):
                collections.append(
                    {"name": "long_term", "entries": len(eng.ai_long_memory.entries)}
                )
            if eng.ai_episodic is not None and hasattr(eng.ai_episodic, "episodes"):
                collections.append({"name": "episodic", "entries": len(eng.ai_episodic.episodes)})
            self.memory_collections = collections
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_workflows(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            workflows = getattr(eng.config, "workflows", None) or {}
            self.workflows = [{"name": name} for name in workflows]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False
