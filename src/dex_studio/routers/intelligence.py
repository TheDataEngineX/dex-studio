"""Intelligence domain — merged ML + AI router.

All routes previously under /ml/* and /ai/* now live here under /intelligence/*.
Adds three new capabilities across the three architecture phases:
  Phase 1: Three-tier Tool Registry, AgentRun persistence, Trace panel
  Phase 2: Embedding collections, search_semantic, ambient context API
  Phase 3: Unified dashboard, Tool Catalog page, Fine-tune page
"""

from __future__ import annotations

import contextlib
import inspect
import threading as _threading
import time
from typing import Annotated, Any

import structlog
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
log = structlog.get_logger().bind(src="router.intelligence")

_SSE_PREFIX = "data: "
_SSE_MEDIA = "text/event-stream"
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_AGENT_TIMEOUT_S = 120
_DRIFT_URL = "/intelligence/drift"
_STAGES = ["development", "staging", "production"]


# ── Ollama circuit breaker ─────────────────────────────────────────────────────


class _OllamaCircuit:
    _THRESHOLD = 3
    _RECOVERY_S = 30.0

    def __init__(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._lock = _threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def allow(self) -> bool:
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open":
                if time.monotonic() - self._opened_at >= self._RECOVERY_S:
                    self._state = "half_open"
                    return True
                return False
            if self._state == "half_open":
                self._state = "probing"
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state in ("half_open", "probing"):
                self._state = "open"
                self._opened_at = time.monotonic()
                self._failures = 0
                return
            self._failures += 1
            if self._failures >= self._THRESHOLD:
                self._state = "open"
                self._opened_at = time.monotonic()


_circuit = _OllamaCircuit()


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _sse(payload: dict[str, Any]) -> str:
    return _SSE_PREFIX + _json.dumps(payload) + "\n\n"


def _ollama_host(eng: Any) -> str:
    try:
        host = getattr(getattr(eng.config.ai, "llm", None), "host", None)
        if host:
            return str(host).rstrip("/")
    except Exception as exc:
        log.warning("ollama host config read failed", error=str(exc))
    return "http://localhost:11434"


def _ollama_model(eng: Any) -> str:
    try:
        return str(eng.config.ai.llm.model)
    except Exception as exc:
        log.warning("ollama model config read failed", error=str(exc))
    return "qwen3:8b"


def _build_schema_ctx(eng: Any) -> str:
    lines: list[str] = []
    for layer in ("gold", "silver", "bronze"):
        try:
            for t in eng.warehouse_tables(layer):
                schema = eng.warehouse_table_schema(t["name"], layer) or []
                cols = ", ".join(c.get("name", str(c)) for c in schema[:10])
                lines.append(f"  {t['name']} ({layer}): {cols}")
        except Exception as exc:
            log.warning("schema context build failed", layer=layer, error=str(exc))
    return "\n".join(lines) or "  (no tables loaded yet)"


def _format_query_result(result: Any) -> dict[str, Any]:
    with contextlib.suppress(Exception):
        if hasattr(result, "to_dict") and hasattr(result, "columns"):
            cols = list(result.columns)
            rows = result.head(50).values.tolist()
            return {"columns": cols, "rows": rows, "row_count": len(result)}
    with contextlib.suppress(Exception):
        if hasattr(result, "fetchall"):
            rows = result.fetchall()
            desc = getattr(result, "description", None) or []
            cols = [d[0] for d in desc]
            return {"columns": cols, "rows": [list(r) for r in rows[:50]], "row_count": len(rows)}
    with contextlib.suppress(Exception):
        if isinstance(result, list) and result and isinstance(result[0], dict):
            cols = list(result[0].keys())
            rows = [list(r.values()) for r in result[:50]]
            return {"columns": cols, "rows": rows, "row_count": len(result)}
    return {"text": str(result)[:2000]}


def _agent_system_prompt(agent_name: str, eng: Any) -> str:
    try:
        cfg = (eng.config.ai.agents or {}).get(agent_name)
        if cfg:
            prompt = str(getattr(cfg, "system_prompt", "") or "")
            if prompt:
                return prompt
    except Exception as exc:
        log.warning("agent system prompt read failed", agent=agent_name, error=str(exc))
    schema_ctx = _build_schema_ctx(eng)
    return (
        f"You are a data assistant. Available tables:\n{schema_ctx}\n\n"
        "When answering data questions write a SQL query in a ```sql block, "
        "then explain the results concisely in plain text."
    )


def _count_memory(obj: Any) -> int:
    for attr in ("entries", "messages", "__len__"):
        with contextlib.suppress(Exception):
            v = getattr(obj, attr, None)
            if callable(v):
                return int(v())
            if v is not None:
                return len(v)  # type: ignore[arg-type]
    return 0


def _run_async_agent(fn: Any, text: str, timeout: float) -> Any:
    import asyncio as _asyncio

    async def _inner() -> Any:
        return await _asyncio.wait_for(fn(text), timeout=timeout)

    return _asyncio.run(_inner())


async def _agent_result(agent: Any, text: str) -> tuple[str, float, int]:
    import asyncio

    t0 = time.monotonic()
    if hasattr(agent, "run"):
        fn = agent.run
    elif hasattr(agent, "chat"):
        fn = agent.chat
    else:
        return str(agent), (time.monotonic() - t0) * 1000, 0

    if inspect.iscoroutinefunction(fn):
        result: Any = await asyncio.to_thread(_run_async_agent, fn, text, _AGENT_TIMEOUT_S)
    else:
        result = await asyncio.to_thread(fn, text)
    latency_ms = (time.monotonic() - t0) * 1000
    tool_calls = 0
    if isinstance(result, dict):
        tool_calls = int(result.get("tool_calls", 0))
        content = (
            result.get("response") or result.get("reply") or result.get("content") or str(result)
        )
        return str(content), latency_ms, tool_calls  # type: ignore[return-value]
    return str(result), latency_ms, tool_calls


# ── Tool registry helpers ──────────────────────────────────────────────────────


def _get_tool_registry(eng: Any) -> Any:
    """Return the DEX Studio tool registry, loading project tools if possible."""
    from dex_studio.tools.registry import get_registry

    registry = get_registry()
    with contextlib.suppress(Exception):
        registry.load_from_config(eng)
    with contextlib.suppress(Exception):
        registry.load_from_project_dir(eng.project_dir)
    return registry


def _tool_rows(eng: Any) -> list[dict[str, Any]]:
    registry = _get_tool_registry(eng)
    rows = []
    for td in registry.list_tools():
        rows.append(
            {
                "name": td.name,
                "description": td.description,
                "tier": td.tier,
                "param_count": len(td.params),
                "params": [
                    {"name": p.name, "type": p.type, "required": p.required, "default": p.default}
                    for p in td.params
                ],
                "source_file": td.source_file,
                "sql_template": td.sql_template[:200] if td.sql_template else "",
            }
        )
    return rows


# ── ML helpers (model registry, predictions, features, drift) ─────────────────


def _model_rows(eng: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in eng.model_registry.list_models():
        with contextlib.suppress(Exception):
            latest = eng.model_registry.get_latest(name)
            rows.append(
                {
                    "name": name,
                    "version": str(latest.version) if latest else "—",
                    "stage": str(latest.stage.value) if latest else "—",
                    "framework": str(latest.parameters.get("framework", "—")) if latest else "—",
                    "parameters": dict(latest.parameters) if latest else {},
                }
            )
    return rows


def _model_data_json(eng: Any) -> str:
    data: dict[str, Any] = {}
    for name in eng.model_registry.list_models():
        with contextlib.suppress(Exception):
            latest = eng.model_registry.get_latest(name)
            if not latest:
                continue
            params = dict(latest.parameters) if latest.parameters else {}
            data[name] = {
                "version": str(latest.version),
                "stage": str(latest.stage.value),
                "framework": str(params.get("framework", "—")),
                "parameters": {k: v for k, v in params.items() if k != "framework"},
            }
    return _json.dumps(data)


def _feature_default(name: str) -> float:
    n = name.lower()
    if "rating" in n:
        return 7.0
    if "count" in n:
        return 10.0
    if n.startswith("g_") or "norm" in n:
        return 0.0
    return 0.0


def _prediction_meta(eng: Any, model_names: list[str]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for name in model_names:
        with contextlib.suppress(Exception):
            art = eng.model_registry.get_latest(name)
            params = getattr(art, "parameters", {}) or {}
            feats = [str(f) for f in (params.get("feature_names") or [])]
            meta[name] = {
                "description": str(getattr(art, "description", "") or ""),
                "features": feats,
                "defaults": {f: _feature_default(f) for f in feats},
            }
    return meta


def _output_meta(model: str) -> dict[str, str]:
    _MAP = {
        "rating_predictor": {
            "label": "Predicted IMDB rating",
            "unit": "/ 10",
            "context": "7+ is well-received; 8+ is acclaimed.",
        },
        "movie_recommender": {
            "label": "Recommendation score",
            "unit": "/ 10",
            "context": "Content-quality score. Use Playground to get actual titles.",
        },
        "genre_classifier": {
            "label": "Predicted decade",
            "unit": "s",
            "context": "e.g. 1990 → 1990s, 2010 → 2010s.",
        },
    }
    return _MAP.get(model, {"label": "Predicted value", "unit": "", "context": ""})


def _parse_prediction(output: str) -> float | None:
    with contextlib.suppress(Exception):
        parsed = _json.loads(output)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], int | float):
            return round(float(parsed[0]), 3)
    return None


def _feature_group_names(fs: Any) -> list[str]:
    if hasattr(fs, "list_feature_groups"):
        return fs.list_feature_groups() or []
    if hasattr(fs, "list_groups"):
        raw = fs.list_groups() or []
        return [g if isinstance(g, str) else str(g.get("name", g)) for g in raw]
    return []


def _feature_consistency(eng: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    available_cols: set[str] = set()
    if eng.feature_store is not None:
        with contextlib.suppress(Exception):
            for group in eng.feature_store.feature_group_info() or []:
                cols = group.get("columns") or []
                if isinstance(cols, list):
                    available_cols.update(str(c) for c in cols)
    for name in eng.model_registry.list_models():
        with contextlib.suppress(Exception):
            art = eng.model_registry.get_latest(name)
            params = getattr(art, "parameters", {}) or {}
            required = [str(f) for f in (params.get("feature_names") or [])]
            if not required:
                continue
            missing = [f for f in required if f not in available_cols]
            results.append(
                {
                    "model": name,
                    "required": required,
                    "available": len(available_cols),
                    "missing": missing,
                    "status": "ok" if not missing else "warn",
                }
            )
    return results


# ── AI dashboard helpers ───────────────────────────────────────────────────────


def _agent_rows(eng: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, cfg in (eng.config.ai.agents if eng.config.ai else {}).items():
        status = "available" if name in eng.agents else "offline"
        raw_model = (
            getattr(cfg, "model", None)
            or getattr(getattr(cfg, "llm", None), "model", None)
            or getattr(cfg, "llm", None)
            or ""
        )
        caps: list[str] = []
        with contextlib.suppress(Exception):
            if getattr(cfg, "tools", None):
                caps.append("tool use")
        if not caps:
            caps = ["chat"]
        rows.append(
            {
                "name": name,
                "type": str(getattr(cfg, "runtime", "builtin")),
                "status": status,
                "model": str(raw_model) if raw_model else "—",
                "system_prompt": str(getattr(cfg, "system_prompt", "") or ""),
                "circuit_state": _circuit.state,
                "timeout": str(getattr(cfg, "timeout", _AGENT_TIMEOUT_S)),
                "capabilities": caps,
            }
        )
    return rows


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def intelligence_dashboard(request: Request, eng: ReadDep) -> HTMLResponse:  # noqa: C901
    # ML stats
    model_names = eng.model_registry.list_models()
    production_count = 0
    top_models: list[dict[str, Any]] = []
    for mname in model_names:
        with contextlib.suppress(Exception):
            latest = eng.model_registry.get_latest(mname)
            stage_val = str(latest.stage.value) if latest else "development"
            if stage_val == "production":
                production_count += 1
            top_models.append(
                {
                    "name": mname,
                    "stage": stage_val,
                    "version": str(latest.version) if latest else "—",
                }
            )

    experiment_count = 0
    leaderboard: list[dict[str, Any]] = []
    if eng.tracker:
        with contextlib.suppress(Exception):
            exps = eng.tracker.list_experiments() or []
            experiment_count = len(exps)
            all_runs: list[dict[str, Any]] = []
            for e in exps:
                exp_id = e.get("id") or e.get("experiment_id", "")
                for r in eng.tracker.list_runs(exp_id) or []:
                    for k, v in r.get("metrics", {}).items():
                        vals = list(v)
                        if vals:
                            all_runs.append(
                                {
                                    "run_id": str(r.get("run_id", r.get("id", ""))),
                                    "exp_name": str(e.get("name", "")),
                                    "primary_metric": round(float(vals[-1]["value"]), 4),
                                    "primary_metric_name": k,
                                }
                            )
                            break
            scored = sorted(
                (r for r in all_runs if r["primary_metric"] is not None),
                key=lambda r: r["primary_metric"] or 0,
                reverse=True,
            )
            leaderboard = scored[:3]

    # AI stats
    agent_count = len(eng.agents)
    registry = _get_tool_registry(eng)
    tool_count = len(registry.list_tools())

    # Run stats from studio DB
    run_stats: dict[str, Any] = {}
    recent_runs: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        from dex_studio.studio_db import get_studio_db

        db = get_studio_db(eng)
        if db:
            run_stats = db.get_run_stats()
            for r in db.get_agent_runs(limit=5):
                recent_runs.append(
                    {
                        "run_id": r["run_id"],
                        "agent": r["agent_name"],
                        "task": r["user_message"][:55]
                        + ("…" if len(r["user_message"]) > 55 else ""),
                        "status": r["status"],
                        "latency_ms": r["total_latency_ms"],
                        "tool_calls": r["tool_calls"],
                        "timestamp": fmt_ts(r["created_at"]),
                    }
                )

    # Embedding collections
    from dex_studio.embeddings import collection_config

    embedding_configs = collection_config(eng)
    built_collections = sum(1 for c in embedding_configs if c.get("built"))

    # Feature groups
    feature_group_count = 0
    if eng.feature_store is not None:
        with contextlib.suppress(Exception):
            feature_group_count = len(_feature_group_names(eng.feature_store))

    ctx = base_ctx(request) | {
        # ML
        "model_count": len(model_names),
        "production_model_count": production_count,
        "experiment_count": experiment_count,
        "feature_group_count": feature_group_count,
        "leaderboard": leaderboard,
        "top_models": top_models[:5],
        # AI
        "agent_count": agent_count,
        "tool_count": tool_count,
        "circuit_state": _circuit.state,
        "agent_statuses": _agent_rows(eng)[:4],
        # Runs
        "run_stats": run_stats,
        "recent_runs": recent_runs,
        # Embeddings
        "embedding_count": len(embedding_configs),
        "built_collection_count": built_collections,
    }
    return render(request, "intelligence/dashboard.html", ctx)


# ── Models ────────────────────────────────────────────────────────────────────


@router.get("/models", response_class=HTMLResponse)
def models(request: Request, eng: ReadDep) -> HTMLResponse:
    model_rows = _model_rows(eng)
    ctx = base_ctx(request) | {
        "models": model_rows,
        "stages": _STAGES,
        "model_data_json": _model_data_json(eng),
    }
    return render(request, "intelligence/models.html", ctx)


@router.post("/models/register")
def register_model(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    version: Annotated[str, Form()] = "1.0.0",
    framework: Annotated[str, Form()] = "",
    artifact_path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        from dataenginex.ml.registry import ModelArtifact, ModelStage

        artifact = ModelArtifact(
            name=name.strip(),
            version=version.strip() or "1.0.0",
            stage=ModelStage.DEVELOPMENT,
            artifact_path=artifact_path.strip(),
            parameters={"framework": framework.strip()} if framework.strip() else {},
        )
        eng.model_registry.register(artifact)
        flash(request, f"Model '{name}' registered.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/intelligence/models", status_code=303)


@router.post("/models/promote/{name}")
def promote_model(
    request: Request,
    eng: WriteDep,
    name: str,
    stage: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        from dataenginex.ml.registry import ModelStage

        latest = eng.model_registry.get_latest(name)
        if latest:
            eng.model_registry.promote(name, latest.version, ModelStage(stage))
            flash(request, f"'{name}' promoted to {stage}.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/intelligence/models", status_code=303)


@router.post("/models/delete/{name}")
def delete_model(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    eng.delete_model(name)
    flash(request, f"Model '{name}' deleted.")
    return RedirectResponse("/intelligence/models", status_code=303)


# ── Experiments ───────────────────────────────────────────────────────────────


@router.get("/experiments", response_class=HTMLResponse)
def experiments(request: Request, eng: ReadDep, exp: str = "") -> HTMLResponse:  # noqa: C901
    exp_list: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    best_run: dict[str, Any] | None = None
    experiment_names: list[str] = []
    metric_names: list[str] = []
    total_runs = 0
    active_experiments = 0
    if eng.tracker:
        try:
            raw = eng.tracker.list_experiments() or []
            experiment_names = [str(e.get("name", "")) for e in raw]
            for e in raw:
                exp_id = e.get("id") or e.get("experiment_id", "")
                exp_runs = eng.tracker.list_runs(exp_id) or []
                run_count = len(exp_runs)
                total_runs += run_count
                if run_count:
                    active_experiments += 1
                exp_list.append(
                    {
                        "name": str(e.get("name", "")),
                        "run_count": run_count,
                        "created_at": exp_runs[0].get("started_at", "—")[:10] if exp_runs else "—",
                    }
                )
            if exp:
                exp_id = next(
                    (
                        e.get("id") or e.get("experiment_id", "")
                        for e in raw
                        if e.get("name") == exp
                    ),
                    exp,
                )
                mnames_seen: list[str] = []
                best_metric: float | None = None
                for r in eng.tracker.list_runs(exp_id):
                    primary_str = "—"
                    primary_val: float | None = None
                    for k, v in r.get("metrics", {}).items():
                        vals = list(v)
                        if vals:
                            mval = round(float(vals[-1]["value"]), 4)
                            primary_str = f"{k}={mval}"
                            primary_val = mval
                            if k not in mnames_seen:
                                mnames_seen.append(k)
                            break
                    runs.append(
                        {
                            "run_id": str(r.get("run_id", r.get("id", ""))),
                            "status": str(r.get("status", "")),
                            "primary_metric": primary_str,
                            "primary_metric_val": primary_val,
                            "primary_metric_name": mnames_seen[0] if mnames_seen else "",
                            "started_at": fmt_ts(r.get("started_at", "")),
                            "ended_at": fmt_ts(r.get("ended_at", "")),
                            "tags": r.get("tags", {}),
                        }
                    )
                    if primary_val is not None and (
                        best_metric is None or primary_val > best_metric
                    ):
                        best_metric = primary_val
                        best_run = runs[-1]
                metric_names = mnames_seen
        except Exception:
            pass

    ctx = base_ctx(request) | {
        "experiments": exp_list,
        "selected_exp": exp,
        "runs": runs,
        "best_run": best_run,
        "experiment_names": experiment_names,
        "metric_names": metric_names,
        "total_runs": total_runs,
        "active_experiments": active_experiments,
    }
    return render(request, "intelligence/experiments.html", ctx)


@router.post("/experiments/new")
def new_experiment(
    request: Request,
    eng: WriteDep,
    exp_name: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        name = exp_name.strip()
        if not name:
            flash(request, "Experiment name is required.", "error")
            return RedirectResponse("/intelligence/experiments", status_code=303)
        if eng.tracker:
            eng.tracker.create_experiment(name)
            flash(request, f"Experiment '{name}' created.")
        else:
            flash(request, "Tracker not configured — add ml.tracker: builtin to dex.yaml.", "error")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/intelligence/experiments", status_code=303)


# ── Predictions ───────────────────────────────────────────────────────────────


@router.get("/predictions", response_class=HTMLResponse)
def predictions(request: Request, eng: ReadDep) -> HTMLResponse:
    model_names = eng.model_registry.list_models()
    meta = _prediction_meta(eng, model_names)
    default_model = model_names[0] if model_names else ""
    out_meta = _output_meta(default_model)
    ctx = base_ctx(request) | {
        "model_names": model_names,
        "selected_model": default_model,
        "model_meta_json": _json.dumps(meta),
        "prediction": None,
        "model_desc": "",
        "prediction_label": out_meta["label"],
        "prediction_unit": out_meta["unit"],
        "prediction_context": out_meta["context"],
        "output": "",
        "error": "",
    }
    return render(request, "intelligence/predictions.html", ctx)


@router.post("/predictions/run", response_class=HTMLResponse)
def run_prediction(
    request: Request,
    eng: WriteDep,
    model: Annotated[str, Form()],
    input_json: Annotated[str, Form()],
) -> HTMLResponse:
    output = ""
    error = ""
    try:
        features = _json.loads(input_json)
        if eng.serving_engine is None:
            error = "Serving engine not available."
        else:
            result = eng.serving_engine.predict(model, features)
            output = _json.dumps(result, indent=2, default=str)
    except ValueError as exc:
        error = f"Invalid JSON: {exc}"
    except FileNotFoundError:
        error = (
            f"Model artifact not found for '{model}'. "
            "Train it via Playground → Ask → finetune() or run the ML pipeline first."
        )
    except Exception as exc:
        error = str(exc)
    prediction = _parse_prediction(output) if (not error and output) else None
    model_desc = ""
    with contextlib.suppress(Exception):
        art = eng.model_registry.get_latest(model)
        model_desc = str(getattr(art, "description", "") or "")
    out_meta = _output_meta(model)
    ctx = base_ctx(request) | {
        "model_names": eng.model_registry.list_models(),
        "selected_model": model,
        "model_meta_json": _json.dumps(_prediction_meta(eng, eng.model_registry.list_models())),
        "prediction": prediction,
        "model_desc": model_desc,
        "prediction_label": out_meta["label"],
        "prediction_unit": out_meta["unit"],
        "prediction_context": out_meta["context"],
        "output": output,
        "error": error,
    }
    if request.headers.get("HX-Request"):
        return render(request, "intelligence/prediction_result.html", ctx)
    return render(request, "intelligence/predictions.html", ctx)


# ── Features ──────────────────────────────────────────────────────────────────


@router.get("/features", response_class=HTMLResponse)
def features(request: Request, eng: ReadDep) -> HTMLResponse:
    groups: list[dict[str, Any]] = []
    if eng.feature_store is not None:
        with contextlib.suppress(Exception):
            groups = eng.feature_store.feature_group_info()
    consistency = _feature_consistency(eng)
    total_features = 0
    total_rows = 0
    for g in groups:
        with contextlib.suppress(Exception):
            cols = g.get("columns") or []
            total_features += len(cols) if isinstance(cols, list) else 0
        with contextlib.suppress(Exception):
            total_rows += int(g.get("row_count") or 0)
    ctx = base_ctx(request) | {
        "feature_groups": groups,
        "consistency": consistency,
        "total_features": total_features,
        "total_rows": total_rows,
    }
    return render(request, "intelligence/features.html", ctx)


# ── Drift ─────────────────────────────────────────────────────────────────────


@router.get("/drift", response_class=HTMLResponse)
def drift(request: Request, eng: ReadDep) -> HTMLResponse:
    features_list: list[dict[str, Any]] = []
    drift_score = "—"
    silver = eng.project_dir / ".dex" / "lakehouse" / "silver"
    silver_tables = [p.stem for p in sorted(silver.glob("*.parquet"))] if silver.exists() else []
    drift_result = request.session.pop("drift_result", None)
    drift_error = request.session.pop("drift_error", None)
    if drift_result:
        features_list = [
            {
                "name": drift_result["feature"],
                "psi": str(drift_result["psi"]),
                "status": "warning" if drift_result["drift_detected"] else "ok",
            }
        ]
        drift_score = str(drift_result["psi"])
    psi_val = 0.0
    with contextlib.suppress(Exception):
        psi_val = float(drift_result["psi"]) if drift_result else 0.0
    overall_drift_status = "critical" if psi_val >= 0.3 else ("warn" if psi_val >= 0.1 else "ok")
    ctx = base_ctx(request) | {
        "drift_score": drift_score,
        "drift_features": features_list,
        "silver_tables": silver_tables,
        "drift_result": drift_result,
        "drift_error": drift_error,
        "overall_drift_status": overall_drift_status,
        "features_drifting": sum(1 for f in features_list if f["status"] == "warning"),
        "avg_drift_score": drift_score if features_list else "—",
        "features_monitored": len(features_list),
    }
    return render(request, "intelligence/drift.html", ctx)


@router.post("/drift/run")
def run_drift(  # noqa: C901
    request: Request,
    eng: WriteDep,
    table: Annotated[str, Form()] = "",
    feature: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        import duckdb
        from dataenginex.ml.drift import DriftDetector

        dex_dir = eng.project_dir / ".dex"
        if not table:
            silver = dex_dir / "lakehouse" / "silver"
            parquets = sorted(silver.glob("*.parquet")) if silver.exists() else []
            if parquets:
                table = parquets[0].stem
        parquet_path = dex_dir / "lakehouse" / "silver" / f"{table}.parquet"
        if not parquet_path.exists():
            request.session["drift_error"] = f"Table '{table}' not found in silver layer."
            return RedirectResponse(_DRIFT_URL, status_code=303)
        abs_path = str(parquet_path.resolve())
        with duckdb.connect(":memory:") as conn:
            row = conn.execute("SELECT COUNT(*) FROM read_parquet($1)", [abs_path]).fetchone()
            total = row[0] if row else 0
            if total < 10:
                request.session["drift_error"] = "Not enough rows for drift detection."
                return RedirectResponse(_DRIFT_URL, status_code=303)
            mid = total // 2
            if not feature:
                cols = conn.execute(
                    "DESCRIBE SELECT * FROM read_parquet($1) LIMIT 1", [abs_path]
                ).fetchall()
                numeric = [c[0] for c in cols if c[1] in ("DOUBLE", "FLOAT", "BIGINT", "INTEGER")]
                feature = numeric[0] if numeric else ""
            if not feature:
                request.session["drift_error"] = "No numeric feature found."
                return RedirectResponse(_DRIFT_URL, status_code=303)
            safe_col = feature.replace('"', '""')
            ref_rows = conn.execute(
                f'SELECT "{safe_col}" FROM read_parquet($1) LIMIT {mid}', [abs_path]
            ).fetchall()
            cur_rows = conn.execute(
                f'SELECT "{safe_col}" FROM read_parquet($1) LIMIT {total - mid} OFFSET {mid}',
                [abs_path],
            ).fetchall()
        reference = [float(r[0]) for r in ref_rows if r[0] is not None]
        current = [float(r[0]) for r in cur_rows if r[0] is not None]
        detector = DriftDetector(psi_threshold=eng.config.ml.drift.threshold)
        report = detector.check_feature(feature, reference, current)
        request.session["drift_result"] = {
            "table": table,
            "feature": feature,
            "psi": round(report.psi, 4),
            "drift_detected": report.drift_detected,
            "severity": report.severity,
        }
    except Exception as exc:
        request.session["drift_error"] = str(exc)
    return RedirectResponse(_DRIFT_URL, status_code=303)


# ── Playground ────────────────────────────────────────────────────────────────


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
    registry = _get_tool_registry(eng)
    ctx = base_ctx(request) | {
        "agent_names": agent_names,
        "selected_agent": selected,
        "catalog_entries": catalog_entries,
        "tool_names": registry.names(),
        "llm_model": llm_model,
        "circuit_state": _circuit.state,
    }
    return render(request, "intelligence/playground.html", ctx)


# ── Agents ────────────────────────────────────────────────────────────────────


@router.get("/agents", response_class=HTMLResponse)
def agents(request: Request, eng: ReadDep) -> HTMLResponse:
    ctx = base_ctx(request) | {"agents": _agent_rows(eng)}
    return render(request, "intelligence/agents.html", ctx)


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
    return RedirectResponse("/intelligence/agents", status_code=303)


@router.post("/agents/delete/{name}")
def delete_agent(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    try:
        eng.delete_agent(name)
        flash(request, f"Agent '{name}' deleted.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/intelligence/agents", status_code=303)


# ── Tool Catalog ───────────────────────────────────────────────────────────────


@router.get("/tools", response_class=HTMLResponse)
def tools(request: Request, eng: ReadDep) -> HTMLResponse:
    rows = _tool_rows(eng)
    builtin_count = sum(1 for t in rows if t["tier"] == "builtin")
    sql_count = sum(1 for t in rows if t["tier"] == "sql")
    python_count = sum(1 for t in rows if t["tier"] == "python")
    ctx = base_ctx(request) | {
        "tools": rows,
        "builtin_count": builtin_count,
        "sql_count": sql_count,
        "python_count": python_count,
    }
    return render(request, "intelligence/tools.html", ctx)


# ── Traces ─────────────────────────────────────────────────────────────────────


@router.get("/traces", response_class=HTMLResponse)
def traces(request: Request, eng: ReadDep, agent: str = "") -> HTMLResponse:
    import json as _json_mod

    trace_rows: list[dict[str, Any]] = []
    run_stats: dict[str, Any] = {}

    with contextlib.suppress(Exception):
        from dex_studio.studio_db import get_studio_db

        db = get_studio_db(eng)
        if db:
            run_stats = db.get_run_stats()
            for r in db.get_agent_runs(limit=100, agent=agent):
                steps = db.get_agent_steps(r["run_id"])
                trace_rows.append(
                    {
                        "id": r["run_id"],
                        "agent": r["agent_name"],
                        "task": r["user_message"][:55]
                        + ("…" if len(r["user_message"]) > 55 else ""),
                        "status": r["status"],
                        "latency_ms": r["total_latency_ms"],
                        "tool_calls": r["tool_calls"],
                        "timestamp": fmt_ts(r["created_at"]),
                        "steps": steps,
                        "input_text": r["user_message"],
                        "output_text": r["final_answer"],
                    }
                )

    # Also pull from ai_audit if available (legacy traces)
    if not trace_rows and eng.ai_audit and hasattr(eng.ai_audit, "get_events"):
        with contextlib.suppress(Exception):
            events = eng.ai_audit.get_events(limit=100) or []
            for e in events:
                _msg = str(getattr(e, "action", ""))
                trace_rows.append(
                    {
                        "id": str(getattr(e, "event_id", "")),
                        "agent": _msg,
                        "message": "",
                        "task": _msg[:45] + ("…" if len(_msg) > 45 else ""),
                        "latency_ms": getattr(e, "details", {}).get("duration_ms", 0),
                        "tool_calls": 0,
                        "status": str(getattr(e, "status", "ok")),
                        "timestamp": fmt_ts(getattr(e, "timestamp", "")),
                        "steps": [],
                        "input_text": "",
                        "output_text": "",
                    }
                )

    total = len(trace_rows)
    errors = sum(1 for t in trace_rows if t.get("status") == "error")
    error_rate = f"{round(errors / total * 100)}%" if total else "0%"

    trace_data: dict[str, Any] = {
        t["id"]: {
            "status": t["status"],
            "task": t["task"],
            "latency_ms": t["latency_ms"],
            "timestamp": t["timestamp"],
            "steps": t.get("steps", []),
            "input_text": t.get("input_text", ""),
            "output_text": t.get("output_text", ""),
        }
        for t in trace_rows
    }

    ctx = base_ctx(request) | {
        "traces": trace_rows,
        "trace_data_json": _json_mod.dumps(trace_data),
        "error_rate": error_rate,
        "agent_filter": agent,
        "run_stats": run_stats,
    }
    return render(request, "intelligence/traces.html", ctx)


# ── Embeddings ────────────────────────────────────────────────────────────────


@router.get("/embeddings", response_class=HTMLResponse)
def embeddings_page(request: Request, eng: ReadDep) -> HTMLResponse:
    from dex_studio.embeddings import collection_config

    collections = collection_config(eng)
    ctx = base_ctx(request) | {
        "collections": collections,
        "built_count": sum(1 for c in collections if c.get("built")),
        "total_vectors": sum(c.get("vector_count", 0) for c in collections),
    }
    return render(request, "intelligence/embeddings.html", ctx)


@router.post("/embeddings/build/{name}")
async def build_embedding(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    import asyncio

    from dex_studio.embeddings import build_collection

    try:
        result = await asyncio.to_thread(build_collection, eng, name)
        if result.get("status") == "ok":
            vc = result.get("vector_count", 0)
            flash(request, f"Collection '{name}' built — {vc:,} vectors.")
        else:
            flash(request, f"Build failed: {result.get('error', 'unknown')}", "error")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/intelligence/embeddings", status_code=303)


# ── Fine-tune ──────────────────────────────────────────────────────────────────


@router.get("/finetune", response_class=HTMLResponse)
def finetune_page(request: Request, eng: ReadDep) -> HTMLResponse:
    gold_tables: list[str] = []
    with contextlib.suppress(Exception):
        gold_tables = [t["name"] for t in (eng.warehouse_tables("gold") or [])]
    model_names = eng.model_registry.list_models()
    ctx = base_ctx(request) | {
        "gold_tables": gold_tables,
        "model_names": model_names,
        "finetune_result": request.session.pop("finetune_result", None),
        "finetune_error": request.session.pop("finetune_error", None),
    }
    return render(request, "intelligence/finetune.html", ctx)


@router.post("/finetune/run")
async def run_finetune(
    request: Request,
    eng: WriteDep,
    feature_set: Annotated[str, Form()],
    target: Annotated[str, Form()],
    algorithm: Annotated[str, Form()] = "random_forest",
    model_name: Annotated[str, Form()] = "",
) -> RedirectResponse:
    import asyncio

    from dex_studio.tools.builtins import _tool_finetune

    try:
        result = await asyncio.to_thread(_tool_finetune, feature_set, target, algorithm, model_name)
        if "error" in result:
            request.session["finetune_error"] = result["error"]
        else:
            request.session["finetune_result"] = result
            flash(request, f"Model '{result.get('model_name')}' trained and registered.")
    except Exception as exc:
        request.session["finetune_error"] = str(exc)
    return RedirectResponse("/intelligence/finetune", status_code=303)


# ── Streaming (SSE) ───────────────────────────────────────────────────────────


def _extract_sql(buffer: str) -> str:
    """Extract SQL from LLM output — handles ```sql``` blocks and TOOL:query/ARGS format."""
    import re as _re

    m = _re.search(r"```sql\s*\n(.+?)\n```", buffer, _re.DOTALL | _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    tool_m = _re.search(
        r"TOOL:\s*query\s*\nARGS:\s*(\{.+?\})\s*(?:\n|$)", buffer, _re.DOTALL | _re.IGNORECASE
    )
    if tool_m:
        import json as _j

        with contextlib.suppress(Exception):
            return str(_j.loads(tool_m.group(1)).get("sql", ""))
    return ""


async def _ollama_chunks(host: str, model: str, messages: list[dict[str, str]]) -> Any:
    import json as _json_std

    import httpx

    async with (
        httpx.AsyncClient(timeout=_AGENT_TIMEOUT_S) as client,
        client.stream(
            "POST",
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {"num_predict": 1024},
            },
        ) as resp,
    ):
        async for raw_line in resp.aiter_lines():
            if not raw_line.strip():
                continue
            with contextlib.suppress(Exception):
                chunk = _json_std.loads(raw_line)
                yield chunk
                if chunk.get("done"):
                    return


async def _sql_tool_sse(sql: str) -> Any:
    yield {"tool_call": "query", "sql": sql}
    try:
        from dex_studio.tools.builtins import _tool_query

        result = _tool_query(sql)
        if inspect.iscoroutine(result):
            result = await result
        yield {"tool_result": _format_query_result(result)}
    except Exception as exc:
        yield {"tool_result": {"text": f"Query error: {exc}"}}


async def _sse_direct(agent_name: str, message: str, eng: Any, run_id: str = "") -> Any:
    """True token-level streaming via Ollama + step-level trace events."""
    from dex_studio.execution import AgentRun

    t0 = time.monotonic()
    model = _ollama_model(eng)
    host = _ollama_host(eng)
    messages = [
        {"role": "system", "content": _agent_system_prompt(agent_name, eng)},
        {"role": "user", "content": message},
    ]

    run = AgentRun(agent_name=agent_name, user_message=message)
    if run_id:
        run.run_id = run_id

    yield _sse({"status": "thinking", "run_id": run.run_id})

    # Step 1 — LLM call
    llm_step = run.add_step("llm")
    yield _sse({"trace": {"step": llm_step.step_id, "type": "llm", "status": "running"}})

    buffer = ""
    try:
        async for chunk in _ollama_chunks(host, model, messages):
            token = chunk.get("message", {}).get("content", "")
            buffer += token
            if token:
                yield _sse({"token": token})
    except Exception as exc:
        llm_step.finish("", "error")
        yield _sse({"trace": {"step": llm_step.step_id, "type": "llm", "status": "error"}})
        yield _sse({"error": f"LLM error: {exc}"})
        run.finish("", "error")
        run.persist(eng)
        return

    llm_step.finish(buffer[:200])
    yield _sse(
        {
            "trace": {
                "step": llm_step.step_id,
                "type": "llm",
                "status": "done",
                "duration_ms": round(llm_step.duration_ms or 0, 1),
            }
        }
    )

    # Step 2 — SQL tool call (handles ```sql``` blocks + TOOL:query/ARGS format)
    tool_calls = 0
    sql_text = _extract_sql(buffer)
    if sql_text:
        tool_step = run.add_step("tool", tool_name="query", inputs={"sql": sql_text[:200]})
        yield _sse(
            {
                "trace": {
                    "step": tool_step.step_id,
                    "type": "tool",
                    "tool": "query",
                    "status": "running",
                }
            }
        )
        async for event in _sql_tool_sse(sql_text):
            yield _sse(event)
        tool_step.finish(sql_text[:100])
        yield _sse(
            {
                "trace": {
                    "step": tool_step.step_id,
                    "type": "tool",
                    "tool": "query",
                    "status": "done",
                    "duration_ms": round(tool_step.duration_ms or 0, 1),
                }
            }
        )
        tool_calls = 1

    latency_ms = (time.monotonic() - t0) * 1000
    run.finish(buffer)
    run.persist(eng)

    yield _sse(
        {
            "done": True,
            "latency_ms": round(latency_ms, 1),
            "tool_calls": tool_calls,
            "run_id": run.run_id,
        }
    )


@router.get("/stream")
async def direct_stream(
    request: Request, eng: JsonReadDep, agent: str = "", message: str = ""
) -> Any:
    from fastapi.responses import StreamingResponse

    if not message or not agent:

        async def _no_args() -> Any:
            yield _sse({"error": "agent and message are required"})

        return StreamingResponse(_no_args(), media_type=_SSE_MEDIA, headers=_SSE_HEADERS)
    return StreamingResponse(
        _sse_direct(agent, message, eng),
        media_type=_SSE_MEDIA,
        headers=_SSE_HEADERS,
    )


# ── JSON API endpoints ────────────────────────────────────────────────────────


@router.post("/chat")
async def chat(request: Request, eng: JsonReadDep) -> Any:
    from fastapi.responses import JSONResponse

    body = await request.json()
    agent_name: str = body.get("agent", "")
    message: str = body.get("message", "")
    if not message:
        return JSONResponse({"error": "No message provided"}, status_code=400)
    agent = eng.agents.get(agent_name)
    if agent is None:
        return JSONResponse(
            {"error": f"Agent '{agent_name}' not found. Available: {list(eng.agents.keys())}"},
            status_code=404,
        )
    try:
        content, latency_ms, tool_calls = await _agent_result(agent, message)
        with contextlib.suppress(Exception):
            if eng.ai_memory and hasattr(eng.ai_memory, "add"):
                eng.ai_memory.add({"role": "user", "content": message})
                eng.ai_memory.add({"role": "assistant", "content": content})
        return JSONResponse(
            {"content": content, "latency_ms": round(latency_ms, 1), "tool_calls": tool_calls}
        )
    except Exception:
        return JSONResponse({"error": "Agent invocation failed"}, status_code=500)


@router.get("/predict/models")
async def predict_models_api(request: Request, eng: JsonReadDep) -> Any:
    """Model names + feature schemas — used by playground Predict mode."""
    import pickle
    from pathlib import Path

    from fastapi.responses import JSONResponse

    models_dir = eng._dex_dir / "models"  # type: ignore[attr-defined]
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
        result.append({"name": name, "stage": latest.get("stage", ""), "features": features})
    return JSONResponse(result)


@router.post("/native")
async def native_call(request: Request, eng: JsonReadDep) -> Any:
    """Direct tool call — no LLM. Body: {tool, args}."""
    from fastapi.responses import JSONResponse

    body = await request.json()
    tool_name: str = body.get("tool", "")
    args: dict[str, Any] = body.get("args") or {}
    if not tool_name:
        return JSONResponse({"error": "tool is required"}, status_code=400)
    registry = _get_tool_registry(eng)
    if not registry.get(tool_name):
        return JSONResponse({"error": f"Tool '{tool_name}' not found"}, status_code=404)
    try:
        t0 = time.monotonic()
        result = registry.call(tool_name, **args)
        if inspect.iscoroutine(result):
            result = await result
        duration_ms = (time.monotonic() - t0) * 1000
        return JSONResponse(
            {"result": result, "tool": tool_name, "duration_ms": round(duration_ms, 1)}
        )
    except Exception:
        return JSONResponse({"error": "An error occurred executing the tool"}, status_code=500)


@router.get("/context")
async def ambient_context(request: Request, eng: JsonReadDep, page: str = "") -> Any:
    """Dex AI pane — full cross-domain context + agents + models."""
    from fastapi.responses import JSONResponse

    ctx_lines: list[str] = [f"Current page: {page}"]

    # ── Data domain ──────────────────────────────────────────────────────────
    with contextlib.suppress(Exception):
        sources = list((eng.config.data.sources or {}).keys())
        if sources:
            ctx_lines.append(f"Sources: {', '.join(sources[:10])}")
    with contextlib.suppress(Exception):
        pipes = list((eng.config.data.pipelines or {}).keys())
        if pipes:
            ctx_lines.append(f"Pipelines: {', '.join(pipes[:10])}")
    with contextlib.suppress(Exception):
        ctx_lines.append(_build_schema_ctx(eng))

    # ── Intelligence domain ───────────────────────────────────────────────────
    with contextlib.suppress(Exception):
        model_names = eng.model_registry.list_models()
        if model_names:
            ctx_lines.append(f"Registered models: {', '.join(model_names)}")
    with contextlib.suppress(Exception):
        experiments = eng.store.list_experiments()
        if experiments:
            ctx_lines.append(f"Experiments: {len(experiments)} tracked")

    # ── System domain ─────────────────────────────────────────────────────────
    with contextlib.suppress(Exception):
        health = eng.health()
        ctx_lines.append(f"System health: {health.get('status', 'unknown')}")

    agents = list(getattr(eng, "agents", {}).keys())
    first_agent = agents[0] if agents else "bot"

    # Model names available for switching (agent names as proxy)
    agent_models: dict[str, str] = {}
    with contextlib.suppress(Exception):
        for aname, aobj in (getattr(eng, "agents", {}) or {}).items():
            model = getattr(getattr(aobj, "config", None), "model", None) or ""
            agent_models[aname] = str(model)

    return JSONResponse(
        {
            "context": "\n".join(ctx_lines),
            "agents": agents,
            "agent": first_agent,
            "agent_models": agent_models,
        }
    )


# ── WebSocket (preserved for real-time use-cases) ─────────────────────────────


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
                with contextlib.suppress(Exception):
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


# ── Stub pages ────────────────────────────────────────────────────────────────


_STUB_TITLES = {
    "/intelligence/hyperopt": "Hyperparameter Optimization",
    "/intelligence/ab-test": "A/B Testing",
    "/intelligence/rag-eval": "RAG Evaluation",
    "/intelligence/hitl": "Human-in-the-Loop",
}


@router.get("/hyperopt", response_class=HTMLResponse)
@router.get("/ab-test", response_class=HTMLResponse)
@router.get("/rag-eval", response_class=HTMLResponse)
@router.get("/hitl", response_class=HTMLResponse)
def intelligence_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _STUB_TITLES)
