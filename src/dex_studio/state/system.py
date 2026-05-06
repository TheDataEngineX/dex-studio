"""Reflex state for system monitoring — health, components, logs, metrics, traces."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import reflex as rx

from dex_studio.state.base import BaseState


class SystemState(BaseState):
    """State for system pages: health checks, component status, audit logs, metrics, traces."""

    health: dict[str, Any] = {}
    components_list: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    log_level: str = "INFO"
    metrics: dict[str, Any] = {}
    traces: list[dict[str, Any]] = []
    last_refreshed: str = ""

    @rx.event(background=True)
    async def start_auto_refresh(self) -> None:
        while True:
            await asyncio.sleep(30)
            async with self:
                await self.load_health()
                await self.load_components()
                self.last_refreshed = datetime.now(UTC).strftime("%H:%M:%S UTC")

    @rx.event
    async def load_health(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            self.health = self._engine().health()
        except Exception as exc:
            self.error = str(exc)
            self.health = {"status": "error", "detail": str(exc)}
        finally:
            self.is_loading = False

    @rx.event
    async def load_components(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            health = self._engine().health()
            self.components_list = [
                {"name": k, "available": v} for k, v in health.get("components", {}).items()
            ]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_logs(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            events = eng.audit.get_events(limit=100)
            self.logs = [e.to_dict() for e in events]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def set_log_level(self, level: str) -> AsyncGenerator[None]:
        self.log_level = level
        async for _ in self.load_logs():  # type: ignore[attr-defined]
            yield

    @rx.event
    async def load_metrics(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            pipe_stats = eng.pipeline_stats()
            self.metrics = {
                "pipeline_total": pipe_stats["total"],
                "pipeline_scheduled": pipe_stats["scheduled"],
                "pipeline_failed": pipe_stats["failed"],
                "pipeline_running": pipe_stats["running"],
                "models": len(eng.model_registry.list_models()),
                "agents": len(eng.agents),
                "lineage_events": len(eng.lineage.all_events),
            }
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
            self.traces = (
                [e.to_dict() for e in eng.ai_audit.all_events] if eng.ai_audit is not None else []
            )
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False
