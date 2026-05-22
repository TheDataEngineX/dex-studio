"""Data domain routes — pipelines, sources, SQL, warehouse, lineage, quality."""

from __future__ import annotations

import contextlib
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio.routers._deps import base_ctx, get_eng, render, require_auth, require_engine
from dex_studio.utils import fmt_cron, fmt_ts

router = APIRouter()

_SOURCE_TYPES = ["csv", "parquet", "duckdb", "postgres", "mysql", "s3", "rest", "kafka"]


@contextlib.contextmanager
def _project_cwd(path: Path) -> Iterator[None]:
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _guard(request: Request) -> RedirectResponse | None:
    return require_auth(request) or require_engine(request)


# ── Dashboard (/data) ────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def data_dashboard(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    stats = eng.pipeline_stats()
    sources = eng.config.data.sources or {}
    layers = eng.warehouse_layers()
    ctx = base_ctx(request) | {
        "stats": stats,
        "source_count": len(sources),
        "layers": layers,
        "active_tab": "data",
    }
    return render(request, "data/dashboard.html", ctx)


# ── Pipelines ────────────────────────────────────────────────────────────────


def _lineage_cls(name: str, layer: str = "") -> str:
    target = layer or name
    for lyr in ("bronze", "silver", "gold"):
        if lyr in target:
            return f":::{lyr}"
    return ":::source"


def _pipeline_status(last: Any) -> str:
    if last is None:
        return "never"
    return "success" if last.success else "failed"


def _build_pipeline_rows(eng: Any) -> list[dict[str, Any]]:
    rows = []
    for name, cfg in (eng.config.data.pipelines or {}).items():
        last = eng.pipeline_last_run(name)
        rows.append(
            {
                "name": name,
                "schedule": fmt_cron(cfg.schedule or "") if cfg.schedule else "—",
                "status": _pipeline_status(last),
                "last_run": fmt_ts(last.timestamp if last else None),
                "duration_ms": f"{last.duration_ms:.0f}" if last and last.duration_ms else "—",
                "rows_in": str(last.rows_input) if last else "—",
                "rows_out": str(last.rows_output) if last else "—",
            }
        )
    return rows


@router.get("/pipelines", response_class=HTMLResponse)
async def pipelines(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    rows = _build_pipeline_rows(eng)
    ctx = base_ctx(request) | {"pipelines": rows, "source_types": _SOURCE_TYPES}
    return render(request, "data/pipelines.html", ctx)


@router.post("/pipelines/run/{name}")
async def run_pipeline(request: Request, name: str) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    try:
        result = eng.run_pipeline(name)
        msg = f"Pipeline '{name}' completed — {result.rows_output} rows out."
        kind = "success" if result.success else "error"
        if not result.success and result.error:
            msg = f"Pipeline '{name}' failed: {result.error}"
    except Exception as exc:
        msg = str(exc)
        kind = "error"
    request.session["flash"] = {"msg": msg, "kind": kind}
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/add")
async def add_pipeline(
    request: Request,
    name: Annotated[str, Form()],
    source: Annotated[str, Form()] = "",
    schedule: Annotated[str, Form()] = "",
    destination: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().add_pipeline(name.strip(), source.strip(), schedule.strip(), destination.strip())
        request.session["flash"] = {"msg": f"Pipeline '{name}' added.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/delete/{name}")
async def delete_pipeline(request: Request, name: str) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().delete_pipeline(name)
        request.session["flash"] = {"msg": f"Pipeline '{name}' deleted.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/{name}/schedule")
async def update_schedule(
    request: Request,
    name: str,
    schedule: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().update_pipeline_schedule(name, schedule.strip() or None)
        request.session["flash"] = {
            "msg": f"Schedule updated for '{name}'.",
            "kind": "success",
        }
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse(f"/data/pipelines/{name}", status_code=303)


@router.get("/pipelines/{name}", response_class=HTMLResponse)
async def pipeline_detail(request: Request, name: str) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    cfg = (eng.config.data.pipelines or {}).get(name)
    if cfg is None:
        return RedirectResponse("/data/pipelines", status_code=303)  # type: ignore[return-value]
    runs = eng.store.get_pipeline_runs(name)
    history = [
        {
            "timestamp": fmt_ts(r.timestamp),
            "success": r.success,
            "rows_input": r.rows_input,
            "rows_output": r.rows_output,
            "duration_ms": f"{r.duration_ms:.0f}" if r.duration_ms else "—",
            "error": r.error or "",
        }
        for r in runs[:20]
    ]
    steps = []
    if hasattr(cfg, "steps") and cfg.steps:
        for s in cfg.steps:
            steps.append(
                {
                    "type": getattr(s, "type", ""),
                    "name": getattr(s, "name", ""),
                    "sql": getattr(s, "sql", ""),
                }
            )
    ctx = base_ctx(request) | {
        "pipeline_name": name,
        "schedule": fmt_cron(cfg.schedule or ""),
        "source": cfg.source or "—",
        "destination": getattr(cfg, "destination", None) or "—",
        "history": history,
        "steps": steps,
    }
    return render(request, "data/pipeline_detail.html", ctx)


# ── Sources ──────────────────────────────────────────────────────────────────


def _build_source_rows(eng: Any) -> list[dict[str, str]]:
    rows = []
    for name, cfg in (eng.config.data.sources or {}).items():
        rows.append(
            {
                "name": name,
                "type": str(getattr(cfg, "type", "—")),
                "status": "active",
            }
        )
    return rows


@router.get("/sources", response_class=HTMLResponse)
async def sources(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    rows = _build_source_rows(eng)
    flash = request.session.pop("flash", None)
    ctx = base_ctx(request) | {
        "sources": rows,
        "source_types": _SOURCE_TYPES,
        "flash": flash,
    }
    return render(request, "data/sources.html", ctx)


@router.get("/sources/{name}", response_class=HTMLResponse)
async def source_detail(request: Request, name: str) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    stats = eng.source_stats(name) or {}
    schema = eng.source_schema(name) or []
    sample_rows = eng.source_sample(name, limit=10) or []
    sample_cols = list(sample_rows[0].keys()) if sample_rows else []
    ctx = base_ctx(request) | {
        "source_name": name,
        "stats": stats,
        "schema": schema,
        "sample_rows": sample_rows,
        "sample_cols": sample_cols,
    }
    return render(request, "data/source_detail.html", ctx)


@router.post("/sources/add")
async def add_source(
    request: Request,
    name: Annotated[str, Form()],
    type_: Annotated[str, Form(alias="type")],
    path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().add_source(name.strip(), type_.strip(), path.strip())
        request.session["flash"] = {"msg": f"Source '{name}' added.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/data/sources", status_code=303)


@router.post("/sources/delete/{name}")
async def delete_source(request: Request, name: str) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().delete_source(name)
        request.session["flash"] = {"msg": f"Source '{name}' removed.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/data/sources", status_code=303)


# ── SQL Console ───────────────────────────────────────────────────────────────


@router.get("/sql", response_class=HTMLResponse)
async def sql_console(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    ctx = base_ctx(request) | {
        "query": "SELECT 1",
        "results": [],
        "columns": [],
        "error": "",
        "exec_ms": None,
    }
    return render(request, "data/sql.html", ctx)


@router.post("/sql/execute", response_class=HTMLResponse)
async def execute_sql(
    request: Request,
    query: Annotated[str, Form()],
) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    results: list[dict[str, Any]] = []
    columns: list[str] = []
    error = ""
    exec_ms: float | None = None
    try:
        t0 = time.monotonic()
        eng = get_eng()
        with _project_cwd(eng.project_dir), duckdb.connect(":memory:") as conn:
            dex_dir = eng.project_dir / ".dex"
            for layer in ("bronze", "silver", "gold"):
                layer_path = dex_dir / "lakehouse" / layer
                if layer_path.exists():
                    for pf in sorted(layer_path.glob("*.parquet")):
                        with contextlib.suppress(Exception):
                            conn.execute(
                                f"CREATE VIEW IF NOT EXISTS {pf.stem} AS"
                                f" SELECT * FROM read_parquet('{pf}')"
                            )
                            conn.execute(
                                f"CREATE VIEW IF NOT EXISTS {layer}_{pf.stem} AS"
                                f" SELECT * FROM read_parquet('{pf}')"
                            )
            cursor = conn.execute(query)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                results = [dict(zip(columns, row, strict=True)) for row in rows]
        exec_ms = (time.monotonic() - t0) * 1000
    except Exception as exc:
        error = str(exc)
    ctx = base_ctx(request) | {
        "query": query,
        "results": results,
        "columns": columns,
        "error": error,
        "exec_ms": exec_ms,
    }
    if request.headers.get("HX-Request"):
        return render(request, "data/sql_results.html", ctx)
    return render(request, "data/sql.html", ctx)


# ── Lakehouse (all layers: Bronze · Silver · Gold) ────────────────────────────


@router.get("/lakehouse", response_class=HTMLResponse)
async def lakehouse(request: Request, layer: str = "") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    layers = eng.warehouse_layers()
    if not layer:
        nonempty = (lyr["name"] for lyr in layers if lyr.get("table_count", 0) > 0)
        layer = next(nonempty, "") or "bronze"
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {
        "layers": layers,
        "active_layer": layer,
        "tables": tables,
    }
    return render(request, "data/lakehouse.html", ctx)


@router.get("/lakehouse/tables", response_class=HTMLResponse)
async def lakehouse_tables_partial(request: Request, layer: str = "bronze") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {"tables": tables, "active_layer": layer}
    return render(request, "data/warehouse_tables.html", ctx)


# ── Warehouse (Gold layer — BI-ready structured data) ─────────────────────────


@router.get("/warehouse", response_class=HTMLResponse)
async def warehouse(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    tables = eng.warehouse_tables("gold")
    ctx = base_ctx(request) | {
        "tables": tables,
        "active_layer": "gold",
    }
    return render(request, "data/warehouse.html", ctx)


@router.get("/warehouse/tables", response_class=HTMLResponse)
async def warehouse_tables_partial(request: Request, layer: str = "bronze") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {"tables": tables, "active_layer": layer}
    return render(request, "data/warehouse_tables.html", ctx)


# ── Lineage ───────────────────────────────────────────────────────────────────


_MERMAID_STYLE = [
    "  classDef source fill:#e8e8e8,stroke:#aaa,color:#333",
    "  classDef bronze fill:#fef3c7,stroke:#d97706,color:#92400e",
    "  classDef silver fill:#dbeafe,stroke:#3b82f6,color:#1e40af",
    "  classDef gold fill:#fef9c3,stroke:#ca8a04,color:#713f12",
]


def _node_id(name: str) -> str:
    # For file paths, use "{layer}_{stem}" to keep IDs short and stable
    if os.sep in name or (name.startswith("/") or name.startswith(".")):
        stem = os.path.splitext(os.path.basename(name))[0]
        for lyr in ("bronze", "silver", "gold"):
            if lyr in name:
                return re.sub(r"\W", "_", f"{lyr}_{stem}")[:64]
        return re.sub(r"\W", "_", stem)[:64]
    return re.sub(r"\W", "_", name)[:64]


def _node_label(name: str) -> str:
    label = os.path.splitext(os.path.basename(name))[0] or name
    return label[:40]


def _node_click_url(node_name: str, is_source: bool) -> str:
    if is_source:
        return f"/data/sources/{node_name}" if node_name and "/" not in node_name else ""
    for layer in ("bronze", "silver", "gold"):
        if layer in node_name:
            return f"/data/warehouse?layer={layer}"
    return ""


def _node_tooltip(name: str, is_source: bool, pipe_names: list[str]) -> str:
    kind = "Source" if is_source else "Table"
    pipes = ", ".join(pipe_names) if pipe_names else "—"
    return f"{kind}: {_node_label(name)} | Pipelines: {pipes}"


def _register_node(
    name: str,
    is_source: bool,
    node_lines: list[str],
    click_lines: list[str],
    seen: set[str],
    pipe_names: list[str],
    layer: str = "",
) -> None:
    nid = _node_id(name)
    if nid in seen:
        return
    node_lines.append(f'  {nid}["{_node_label(name)}"]{_lineage_cls(name, layer)}')
    seen.add(nid)
    url = _node_click_url(name, is_source)
    if url:
        tip = _node_tooltip(name, is_source, pipe_names).replace('"', "'")
        click_lines.append(f'  click {nid} "{url}" "{tip}"')


def _build_mermaid(events: list[dict[str, Any]]) -> str:
    node_lines: list[str] = []
    click_lines: list[str] = []
    edge_lines: list[str] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    # Gather per-node pipeline names for tooltips
    node_pipes: dict[str, list[str]] = {}
    for e in events:
        for node in (e["source"], e["target"]):
            node_pipes.setdefault(node, [])
            pn = e["pipeline_name"]
            if pn and pn not in node_pipes[node]:
                node_pipes[node].append(pn)
    for e in events:
        src_name, tgt_name, pipe_name = e["source"], e["target"], e["pipeline_name"]
        layer = e.get("layer", "")
        _register_node(
            src_name, True, node_lines, click_lines, seen_nodes, node_pipes.get(src_name, [])
        )
        _register_node(
            tgt_name,
            False,
            node_lines,
            click_lines,
            seen_nodes,
            node_pipes.get(tgt_name, []),
            layer,
        )
        edge_key = (_node_id(src_name), _node_id(tgt_name), _node_id(pipe_name))
        if edge_key not in seen_edges:
            edge_lines.append(f"  {edge_key[0]} -->|{_node_label(pipe_name)}| {edge_key[1]}")
            seen_edges.add(edge_key)
    return "\n".join(["flowchart LR", *node_lines, *edge_lines, *click_lines, *_MERMAID_STYLE])


def _get_lineage_events(eng: Any, pipeline: str = "") -> list[dict[str, Any]]:
    events = [
        {
            "id": getattr(e, "event_id", ""),
            "source": getattr(e, "source", ""),
            "target": getattr(e, "destination", ""),
            "layer": getattr(e, "layer", ""),
            "pipeline_name": getattr(e, "pipeline_name", ""),
            "timestamp": fmt_ts(getattr(e, "timestamp", "")),
        }
        for e in (eng.lineage.all_events if eng.lineage else [])
    ]
    if pipeline:
        events = [e for e in events if e["pipeline_name"] == pipeline]
    return events


@router.get("/lineage/graph-partial", response_class=HTMLResponse)
async def lineage_graph_partial(request: Request, pipeline: str = "") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    events = _get_lineage_events(eng, pipeline)
    diagram = _build_mermaid(events) if events else ""
    if diagram:
        html = f'<pre class="mermaid" style="background:transparent;font-size:13px">{diagram}</pre>'
    else:
        html = '<p style="font-size:13px;color:var(--gray-9)">No graph data available.</p>'
    return HTMLResponse(html)


@router.get("/lineage", response_class=HTMLResponse)
async def lineage(request: Request, pipeline: str = "", view: str = "table") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    all_events = _get_lineage_events(eng, pipeline)
    pipeline_names = sorted({e["pipeline_name"] for e in all_events if e["pipeline_name"]})
    ctx = base_ctx(request) | {
        "events": all_events,
        "pipeline_names": pipeline_names,
        "filter_pipeline": pipeline,
        "view": view,
        "mermaid_diagram": _build_mermaid(all_events) if all_events else "",
    }
    return render(request, "data/lineage.html", ctx)


# ── Data Quality ──────────────────────────────────────────────────────────────


@router.get("/quality", response_class=HTMLResponse)
async def quality(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    history = eng.quality_history()
    runs = history.get("runs", [])
    # Build flat check rows from latest run
    checks: list[dict[str, Any]] = []
    score_pct = "—"
    if runs:
        latest = runs[0]
        results = latest.get("results", {})
        scores = []
        for table, r in results.items():
            if r is None:
                continue
            s = r.get("score", 0.0)
            scores.append(s)
            checks.append(
                {
                    "table": table,
                    "score": f"{s * 100:.0f}%",
                    "completeness": f"{r.get('completeness', 0) * 100:.0f}%",
                    "uniqueness": f"{r.get('uniqueness', 0) * 100:.0f}%",
                    "passed": r.get("passed", False),
                }
            )
        if scores:
            score_pct = f"{sum(scores) / len(scores) * 100:.0f}%"
    ctx = base_ctx(request) | {
        "score_pct": score_pct,
        "checks": checks,
        "run_count": len(runs),
    }
    return render(request, "data/quality.html", ctx)


@router.post("/quality/run")
async def run_quality(request: Request) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().quality_check_all_tables()
        request.session["flash"] = {"msg": "Quality checks complete.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/data/quality", status_code=303)


# ── Catalog (alias for sources) ───────────────────────────────────────────────


@router.get("/catalog", response_class=HTMLResponse)
async def catalog(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    entries: list[dict[str, Any]] = []
    layer_colors = {"bronze": "orange", "silver": "indigo", "gold": "amber"}
    for layer in ("bronze", "silver", "gold"):
        for table in eng.warehouse_tables(layer):
            schema = eng.warehouse_table_schema(table["name"], layer) or []
            entries.append(
                {
                    "name": table["name"],
                    "layer": layer,
                    "layer_color": layer_colors[layer],
                    "row_count": table.get("row_count", "—"),
                    "column_count": len(schema),
                    "size": table.get("size", "—"),
                    "columns": schema,
                }
            )
    ctx = base_ctx(request) | {"entries": entries, "active_tab": "data"}
    return render(request, "data/catalog.html", ctx)


# ── Asset Graph / Contracts / Templates (stubs) ───────────────────────────────


@router.get("/asset-graph", response_class=HTMLResponse)
@router.get("/contracts", response_class=HTMLResponse)
@router.get("/templates", response_class=HTMLResponse)
async def data_stub(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    page_titles = {
        "/data/asset-graph": "Asset Graph",
        "/data/contracts": "Data Contracts",
        "/data/templates": "Pipeline Templates",
    }
    ctx = base_ctx(request) | {"page_title": page_titles.get(request.url.path, "Coming Soon")}
    return render(request, "stub.html", ctx)
