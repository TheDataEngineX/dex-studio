"""AI domain routes — agents, playground (WebSocket), memory, tools, traces."""

from __future__ import annotations

import contextlib
import inspect
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio.routers._deps import base_ctx, get_eng, render, require_auth, require_engine
from dex_studio.utils import fmt_ts

router = APIRouter()


async def _agent_result(agent: Any, text: str) -> str:
    """Invoke agent and return string response."""
    if hasattr(agent, "run"):
        result: Any = agent.run(text)
    elif hasattr(agent, "chat"):
        result = agent.chat(text)
    else:
        return str(agent)
    if inspect.iscoroutine(result):
        result = await result
    if isinstance(result, dict):
        return result.get("response") or result.get("reply") or result.get("content") or str(result)  # type: ignore[return-value]
    return str(result)


def _count_memory(obj: Any) -> int:
    """Count entries in a memory store, handling various attribute shapes."""
    for attr in ("entries", "messages", "__len__"):
        with contextlib.suppress(Exception):
            v = getattr(obj, attr, None)
            if callable(v):
                return int(v())
            if v is not None:
                return len(v)  # type: ignore[arg-type]
    return 0


def _guard(request: Request) -> RedirectResponse | None:
    return require_auth(request) or require_engine(request)


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ai_dashboard(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    agent_count = len(eng.agents)
    tool_count = 0
    with contextlib.suppress(Exception):
        from dataenginex.ai.tools import tool_registry

        tool_count = len(tool_registry.list())
    mem_count = 0
    if eng.ai_memory and hasattr(eng.ai_memory, "messages"):
        mem_count = len(eng.ai_memory.messages)
    ctx = base_ctx(request) | {
        "agent_count": agent_count,
        "tool_count": tool_count,
        "memory_count": mem_count,
    }
    return render(request, "ai/dashboard.html", ctx)


# ── Agents ────────────────────────────────────────────────────────────────────


def _agent_rows(eng: Any) -> list[dict[str, str]]:
    rows = []
    for name, cfg in (eng.config.ai.agents if eng.config.ai else {}).items():
        status = "available" if name in eng.agents else "offline"
        rows.append(
            {
                "name": name,
                "type": str(getattr(cfg, "runtime", "builtin")),
                "status": status,
            }
        )
    return rows


@router.get("/agents", response_class=HTMLResponse)
async def agents(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    flash = request.session.pop("flash", None)
    ctx = base_ctx(request) | {"agents": _agent_rows(get_eng()), "flash": flash}
    return render(request, "ai/agents.html", ctx)


@router.post("/agents/add")
async def add_agent(
    request: Request,
    name: Annotated[str, Form()],
    runtime: Annotated[str, Form()] = "builtin",
    system_prompt: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().add_agent(name.strip(), runtime.strip(), system_prompt.strip())
        request.session["flash"] = {"msg": f"Agent '{name}' created.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/ai/agents", status_code=303)


@router.post("/agents/delete/{name}")
async def delete_agent(request: Request, name: str) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().delete_agent(name)
        request.session["flash"] = {"msg": f"Agent '{name}' deleted.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/ai/agents", status_code=303)


# ── Playground (HTTP + WebSocket) ─────────────────────────────────────────────


@router.get("/playground", response_class=HTMLResponse)
async def playground(request: Request, agent: str = "") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    agent_names = list(eng.agents.keys())
    selected = agent or (agent_names[0] if agent_names else "")
    ctx = base_ctx(request) | {
        "agent_names": agent_names,
        "selected_agent": selected,
    }
    return render(request, "ai/playground.html", ctx)


@router.websocket("/playground/ws/{agent_name}")
async def playground_ws(websocket: WebSocket, agent_name: str) -> None:
    await websocket.accept()
    eng = get_eng()
    agent = eng.agents.get(agent_name)
    try:
        while True:
            text = await websocket.receive_text()
            if not text.strip():
                continue
            if agent is None:
                await websocket.send_json(
                    {"role": "assistant", "content": f"Agent '{agent_name}' not available."}
                )
                continue
            try:
                content = await _agent_result(agent, text)
                if eng.ai_memory and hasattr(eng.ai_memory, "add"):
                    eng.ai_memory.add({"role": "user", "content": text})
                    eng.ai_memory.add({"role": "assistant", "content": content})
                await websocket.send_json({"role": "assistant", "content": content})
            except Exception as exc:
                await websocket.send_json({"role": "error", "content": str(exc)})
    except WebSocketDisconnect:
        pass


# ── Traces ────────────────────────────────────────────────────────────────────


@router.get("/traces", response_class=HTMLResponse)
async def traces(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    trace_rows: list[dict[str, str]] = []
    if eng.ai_audit and hasattr(eng.ai_audit, "get_events"):
        try:
            events = eng.ai_audit.get_events(limit=50) or []
            for e in events:
                trace_rows.append(
                    {
                        "id": str(getattr(e, "event_id", "")),
                        "name": str(getattr(e, "action", "")),
                        "duration_ms": str(getattr(e, "details", {}).get("duration_ms", "—")),
                        "status": str(getattr(e, "status", "")),
                        "timestamp": fmt_ts(getattr(e, "timestamp", "")),
                    }
                )
        except Exception:
            pass
    ctx = base_ctx(request) | {"traces": trace_rows}
    return render(request, "ai/traces.html", ctx)


# ── Tools ─────────────────────────────────────────────────────────────────────


@router.get("/tools", response_class=HTMLResponse)
async def tools(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    tool_rows: list[dict[str, str]] = []
    try:
        from dataenginex.ai.tools import tool_registry

        for t in tool_registry.list():
            tool_rows.append(
                {
                    "name": str(getattr(t, "name", t)),
                    "description": str(getattr(t, "description", "")),
                }
            )
    except Exception:
        pass
    ctx = base_ctx(request) | {"tools": tool_rows}
    return render(request, "ai/tools.html", ctx)


# ── Memory ────────────────────────────────────────────────────────────────────


@router.get("/memory", response_class=HTMLResponse)
async def memory(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    mem_defs = [
        ("short", eng.ai_memory, "Short-term"),
        ("long", eng.ai_long_memory, "Long-term"),
        ("episodic", eng.ai_episodic, "Episodic"),
    ]
    collections: list[dict[str, str]] = [
        {"name": label, "entries": str(_count_memory(obj)), "type": kind}
        for kind, obj, label in mem_defs
        if obj is not None
    ]

    ctx = base_ctx(request) | {"collections": collections}
    return render(request, "ai/memory.html", ctx)


# ── Stubs ─────────────────────────────────────────────────────────────────────


@router.get("/workflows", response_class=HTMLResponse)
@router.get("/router", response_class=HTMLResponse)
@router.get("/cost", response_class=HTMLResponse)
@router.get("/hitl", response_class=HTMLResponse)
@router.get("/sandbox", response_class=HTMLResponse)
@router.get("/rag-eval", response_class=HTMLResponse)
@router.get("/retrieval", response_class=HTMLResponse)
@router.get("/vectors", response_class=HTMLResponse)
@router.get("/collections", response_class=HTMLResponse)
async def ai_stub(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    titles = {
        "/ai/workflows": "Workflows",
        "/ai/router": "Model Router",
        "/ai/cost": "Cost Tracking",
        "/ai/hitl": "Human-in-the-Loop",
        "/ai/sandbox": "Agent Sandbox",
        "/ai/rag-eval": "RAG Evaluation",
        "/ai/retrieval": "Retrieval",
        "/ai/vectors": "Vector Store",
        "/ai/collections": "Collections",
    }
    ctx = base_ctx(request) | {"page_title": titles.get(request.url.path, "Coming Soon")}
    return render(request, "stub.html", ctx)
