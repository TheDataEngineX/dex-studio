"""AI domain routes — agents, playground (WebSocket + SSE), memory, tools, traces."""

from __future__ import annotations

import contextlib
import inspect
import time
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio import _json
from dex_studio.auth import is_authenticated
from dex_studio.routers._deps import (
    JsonReadDep,
    ReadDep,
    WriteDep,
    base_ctx,
    flash,
    get_eng,
    render,
    stub_page,
)
from dex_studio.utils import fmt_ts

router = APIRouter()

_SSE_PREFIX = "data: "
_SSE_MEDIA = "text/event-stream"


_AGENT_TIMEOUT_S = 30


async def _agent_result(agent: Any, text: str) -> tuple[str, float, int]:
    """Invoke agent and return (response, latency_ms, tool_calls)."""
    import asyncio

    t0 = time.monotonic()
    if hasattr(agent, "run"):
        fn = agent.run
    elif hasattr(agent, "chat"):
        fn = agent.chat
    else:
        return str(agent), (time.monotonic() - t0) * 1000, 0

    if inspect.iscoroutinefunction(fn):
        result: Any = await asyncio.wait_for(fn(text), timeout=_AGENT_TIMEOUT_S)
    else:
        result = await asyncio.wait_for(asyncio.to_thread(fn, text), timeout=_AGENT_TIMEOUT_S)
    latency_ms = (time.monotonic() - t0) * 1000
    tool_calls = 0
    if isinstance(result, dict):
        tool_calls = int(result.get("tool_calls", 0))
        content = (
            result.get("response") or result.get("reply") or result.get("content") or str(result)
        )
        return str(content), latency_ms, tool_calls  # type: ignore[return-value]
    return str(result), latency_ms, tool_calls


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


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def ai_dashboard(request: Request, eng: ReadDep) -> HTMLResponse:
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
        # best-effort: pick model from cfg.model or cfg.llm.model or cfg.llm
        raw_model = (
            getattr(cfg, "model", None)
            or getattr(getattr(cfg, "llm", None), "model", None)
            or getattr(cfg, "llm", None)
            or ""
        )
        rows.append(
            {
                "name": name,
                "type": str(getattr(cfg, "runtime", "builtin")),
                "status": status,
                "model": str(raw_model) if raw_model else "—",
                "system_prompt": str(getattr(cfg, "system_prompt", "") or ""),
            }
        )
    return rows


@router.get("/agents", response_class=HTMLResponse)
def agents(request: Request, eng: ReadDep) -> HTMLResponse:
    ctx = base_ctx(request) | {"agents": _agent_rows(eng)}
    return render(request, "ai/agents.html", ctx)


@router.post("/agents/add")
def add_agent(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    runtime: Annotated[str, Form()] = "builtin",
    system_prompt: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        eng.add_agent(name.strip(), runtime.strip(), system_prompt.strip())
        flash(request, f"Agent '{name}' created.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/ai/agents", status_code=303)


@router.post("/agents/delete/{name}")
def delete_agent(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    try:
        eng.delete_agent(name)
        flash(request, f"Agent '{name}' deleted.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/ai/agents", status_code=303)


# ── Playground (HTTP + WebSocket) ─────────────────────────────────────────────


@router.get("/playground", response_class=HTMLResponse)
def playground(request: Request, eng: ReadDep, agent: str = "") -> HTMLResponse:
    agent_names = list(eng.agents.keys())
    selected = agent if agent in agent_names else (agent_names[0] if agent_names else "")
    catalog_entries: list[dict[str, Any]] = []
    for layer in ("bronze", "silver", "gold"):
        for tbl in eng.warehouse_tables(layer):
            schema = eng.warehouse_table_schema(tbl["name"], layer) or []
            catalog_entries.append(
                {"name": tbl["name"], "layer": layer, "column_count": len(schema)}
            )
    llm_model = ""
    with contextlib.suppress(Exception):
        llm_model = str(eng.config.ai.llm.model)
    from dataenginex.ai.tools import tool_registry as _tr

    ctx = base_ctx(request) | {
        "agent_names": agent_names,
        "selected_agent": selected,
        "catalog_entries": catalog_entries,
        "tool_names": _tr.list(),
        "llm_model": llm_model,
    }
    return render(request, "ai/playground.html", ctx)


@router.post("/chat")
async def chat(request: Request, eng: JsonReadDep) -> Any:
    """Simple JSON chat endpoint — runs the named agent and returns the response."""
    from fastapi.responses import JSONResponse

    body = await request.json()
    agent_name: str = body.get("agent", "")
    message: str = body.get("message", "")
    if not message:
        return JSONResponse({"error": "No message provided"}, status_code=400)
    agent = eng.agents.get(agent_name)
    if agent is None:
        available = list(eng.agents.keys())
        return JSONResponse(
            {"error": f"Agent '{agent_name}' not found. Available: {available}"},
            status_code=404,
        )
    try:
        content, latency_ms, tool_calls = await _agent_result(agent, message)
        with contextlib.suppress(Exception):
            if eng.ai_memory and hasattr(eng.ai_memory, "add"):
                eng.ai_memory.add({"role": "user", "content": message})
                eng.ai_memory.add({"role": "assistant", "content": content})
        with contextlib.suppress(Exception):
            metrics = getattr(eng, "ai_metrics", None)
            if metrics:
                metrics.increment_requests(agent_name)
                metrics.record_latency(agent_name, latency_ms / 1000)
        return JSONResponse(
            {
                "content": content,
                "latency_ms": round(latency_ms, 1),
                "tool_calls": tool_calls,
            }
        )
    except Exception:
        return JSONResponse({"error": "Agent invocation failed"}, status_code=500)


@router.get("/predict/models")
async def predict_models(request: Request, eng: JsonReadDep) -> Any:
    """Return model names + feature schemas by introspecting pkl files."""
    from fastapi.responses import JSONResponse

    models_dir = eng._dex_dir / "models"  # type: ignore[attr-defined]
    import pickle
    from pathlib import Path

    registry_path = models_dir / "registry.json"
    model_map: dict[str, list[Any]] = {}
    if registry_path.exists():
        with contextlib.suppress(Exception):
            model_map = _json.loads(registry_path.read_text())

    result = []
    for name, versions in model_map.items():
        if not versions:
            continue
        latest = versions[-1]
        artifact = Path(latest.get("artifact_path", ""))
        features: list[dict[str, Any]] = []
        if artifact.exists():
            with contextlib.suppress(Exception):
                with open(artifact, "rb") as f:
                    mdl = pickle.load(f)
                fn = getattr(mdl, "feature_names_in_", None)
                if fn is not None:
                    features = [{"name": str(n), "type": "number"} for n in fn]
        result.append(
            {
                "name": name,
                "stage": latest.get("stage", ""),
                "features": features,
            }
        )
    return JSONResponse(result)


@router.post("/native")
async def native_call(request: Request, _: JsonReadDep) -> Any:
    """Direct tool call — no LLM. Body: {tool, args}. Returns {result, tool, duration_ms}."""
    from fastapi.responses import JSONResponse

    body = await request.json()
    tool_name: str = body.get("tool", "")
    args: dict[str, Any] = body.get("args") or {}
    if not tool_name:
        return JSONResponse({"error": "tool is required"}, status_code=400)
    try:
        from dataenginex.ai.tools import tool_registry

        t0 = time.monotonic()
        result = tool_registry.call(tool_name, **args)
        if inspect.iscoroutine(result):
            result = await result
        duration_ms = (time.monotonic() - t0) * 1000
        return JSONResponse(
            {"result": result, "tool": tool_name, "duration_ms": round(duration_ms, 1)}
        )
    except KeyError:
        return JSONResponse({"error": f"Tool '{tool_name}' not found"}, status_code=404)
    except Exception:
        return JSONResponse({"error": "Tool invocation failed"}, status_code=500)


def _sse(payload: dict[str, Any]) -> str:

    return _SSE_PREFIX + _json.dumps(payload) + "\n\n"


async def _sse_generate(
    agent_name: str,
    agent_obj: Any,
    message: str,
    eng: Any,
) -> Any:
    """Async generator that streams agent response tokens as SSE events."""
    import asyncio

    if agent_obj is None:
        yield _sse({"error": f"Agent '{agent_name}' not found"})
        return

    try:
        content, latency_ms, tool_calls = await _agent_result(agent_obj, message)
    except TimeoutError:
        msg = f"Agent timed out after {_AGENT_TIMEOUT_S}s — is the LLM backend running?"
        yield _sse({"error": msg})
        return
    except Exception:
        yield _sse({"error": "Agent invocation failed"})
        return

    with contextlib.suppress(Exception):
        if eng.ai_memory and hasattr(eng.ai_memory, "add"):
            eng.ai_memory.add({"role": "user", "content": message})
            eng.ai_memory.add({"role": "assistant", "content": content})
    with contextlib.suppress(Exception):
        if eng.ai_metrics:
            eng.ai_metrics.increment_requests(agent_name)
            eng.ai_metrics.record_latency(agent_name, latency_ms / 1000)

    words = content.split(" ")
    for i, word in enumerate(words):
        chunk = word + (" " if i < len(words) - 1 else "")
        yield _sse({"token": chunk})
        await asyncio.sleep(0.01)

    yield _sse({"done": True, "latency_ms": round(latency_ms, 1), "tool_calls": tool_calls})


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/chat/stream")
async def chat_stream(
    request: Request, eng: JsonReadDep, agent: str = "", message: str = ""
) -> Any:
    """SSE streaming endpoint — yields tokens as the agent generates them."""
    from fastapi.responses import StreamingResponse

    if not message or not agent:

        async def _bad() -> Any:
            yield _sse({"error": "agent and message are required"})

        return StreamingResponse(_bad(), media_type=_SSE_MEDIA, headers=_SSE_HEADERS)

    return StreamingResponse(
        _sse_generate(agent, eng.agents.get(agent), message, eng),
        media_type=_SSE_MEDIA,
        headers=_SSE_HEADERS,
    )


@router.websocket("/playground/ws/{agent_name}")
async def playground_ws(websocket: WebSocket, agent_name: str) -> None:
    if not is_authenticated(websocket):  # type: ignore[arg-type]
        await websocket.close(code=3000)
        return
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
                content, latency_ms, tool_calls = await _agent_result(agent, text)
                if eng.ai_memory and hasattr(eng.ai_memory, "add"):
                    eng.ai_memory.add({"role": "user", "content": text})
                    eng.ai_memory.add({"role": "assistant", "content": content})
                await websocket.send_json(
                    {
                        "role": "assistant",
                        "content": content,
                        "latency_ms": round(latency_ms, 1),
                        "tool_calls": tool_calls,
                    }
                )
            except Exception as exc:
                await websocket.send_json({"role": "error", "content": str(exc)})
    except WebSocketDisconnect:
        pass


# ── Traces ────────────────────────────────────────────────────────────────────


@router.get("/traces", response_class=HTMLResponse)
def traces(request: Request, eng: ReadDep) -> HTMLResponse:
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
def tools(request: Request, _: ReadDep) -> HTMLResponse:
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
def memory(request: Request, eng: ReadDep) -> HTMLResponse:
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


# ── Workflows ─────────────────────────────────────────────────────────────────


@router.get("/workflows", response_class=HTMLResponse)
def ai_workflows(request: Request, eng: ReadDep) -> HTMLResponse:
    workflows: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        ai_cfg = getattr(eng.config, "ai", None)
        raw_wfs = getattr(ai_cfg, "workflows", None) or {}
        if hasattr(raw_wfs, "items"):
            for name, wcfg in raw_wfs.items():
                workflows.append(
                    {
                        "name": name,
                        "schedule": str(getattr(wcfg, "schedule", "") or ""),
                        "status": "idle",
                        "steps": len(getattr(wcfg, "steps", []) or []),
                        "owner": str(getattr(wcfg, "owner", "") or ""),
                    }
                )
    ctx = base_ctx(request) | {
        "workflows": workflows,
        "active_tab": "ai",
    }
    return render(request, "ai/workflows.html", ctx)


# ── Stubs ─────────────────────────────────────────────────────────────────────

_AI_STUB_TITLES = {
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


@router.get("/router", response_class=HTMLResponse)
@router.get("/cost", response_class=HTMLResponse)
@router.get("/hitl", response_class=HTMLResponse)
@router.get("/sandbox", response_class=HTMLResponse)
@router.get("/rag-eval", response_class=HTMLResponse)
@router.get("/retrieval", response_class=HTMLResponse)
@router.get("/vectors", response_class=HTMLResponse)
@router.get("/collections", response_class=HTMLResponse)
def ai_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _AI_STUB_TITLES)
