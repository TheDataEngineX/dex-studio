"""Intelligence execution engine — AgentRun with step-level observability.

Every agent interaction produces an AgentRun persisted to studio.db.
Each run contains ordered AgentSteps (llm / tool / retrieval).
SSE events carry both content tokens and trace events so the UI can
render a live execution timeline alongside the streamed answer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class AgentStep:
    step_id: int
    type: Literal["llm", "tool", "retrieval"]
    tool_name: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    output_preview: str = ""
    status: Literal["running", "done", "error"] = "running"
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    tokens: int = 0

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000

    def finish(self, output: str = "", status: Literal["done", "error"] = "done") -> None:
        self.ended_at = time.monotonic()
        self.status = status
        self.output_preview = output[:200]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "type": self.type,
            "tool_name": self.tool_name,
            "inputs": self.inputs,
            "output_preview": self.output_preview,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 1) if self.duration_ms is not None else None,
            "tokens": self.tokens,
        }


@dataclass
class AgentRun:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_name: str = ""
    user_message: str = ""
    steps: list[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    total_latency_ms: float = 0.0
    tool_calls: int = 0
    status: Literal["running", "done", "error"] = "running"
    _t0: float = field(default_factory=time.monotonic, repr=False)

    def add_step(self, step_type: Literal["llm", "tool", "retrieval"], **kwargs: Any) -> AgentStep:
        step = AgentStep(step_id=len(self.steps) + 1, type=step_type, **kwargs)
        self.steps.append(step)
        return step

    def finish(self, answer: str, status: Literal["done", "error"] = "done") -> None:
        self.final_answer = answer
        self.status = status
        self.total_latency_ms = (time.monotonic() - self._t0) * 1000
        self.tool_calls = sum(1 for s in self.steps if s.type == "tool")

    def to_trace_event(self, step: AgentStep) -> dict[str, Any]:
        """SSE-compatible trace event for a step."""
        return {
            "trace": {
                "step": step.step_id,
                "type": step.type,
                "tool": step.tool_name,
                "status": step.status,
                "duration_ms": round(step.duration_ms, 1) if step.duration_ms is not None else None,
                "preview": step.output_preview,
            }
        }

    def persist(self, eng: Any) -> None:
        """Write run + steps to studio.db."""
        import contextlib

        with contextlib.suppress(Exception):
            from dex_studio.studio_db import get_studio_db

            db = get_studio_db(eng)
            if db:
                db.record_agent_run(self)


def _run_id() -> str:
    return uuid.uuid4().hex[:16]
