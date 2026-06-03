"""Data domain routes — pipelines, sources, SQL, warehouse, lineage, quality."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio.routers._deps import (
    base_ctx,
    flash,
    get_eng,
    guard,
    render,
    stub_page,
)
from dex_studio.utils import fmt_cron, fmt_ts

router = APIRouter()

_SOURCE_TYPES = [
    "csv",
    "parquet",
    "duckdb",
    "postgres",
    "mysql",
    "s3",
    "rest",
    "kafka",
    "spark",
    "dbt",
]


# ── Dashboard (/data) ────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def data_dashboard(request: Request) -> HTMLResponse:
    if redir := guard(request):
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


def _lineage_nid(s: str) -> str:
    return re.sub(r"\W+", "_", s).strip("_")[:40]


def _lineage_layer(p_name: str, p_cfg: Any) -> str:
    tgt = getattr(p_cfg, "target", None) or {}
    explicit: str | None = str(tgt["layer"]) if isinstance(tgt, dict) and tgt.get("layer") else None
    if explicit:
        return explicit
    if p_name.startswith("bronze_"):
        return "bronze"
    if p_name.startswith("gold_"):
        return "gold"
    return "silver"


def _lineage_nodes(by_layer: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    lane_x = {"source": 2, "bronze": 27, "silver": 52, "gold": 77}
    nodes: list[dict[str, Any]] = []
    node_ids: dict[str, str] = {}
    for layer, names in by_layer.items():
        n = len(names)
        for i, name in enumerate(sorted(names)):
            y = round((i + 1) * 88 / max(n + 1, 2)) + 5
            nid = _lineage_nid(name)
            node_ids[name] = nid
            nodes.append(
                {
                    "id": nid,
                    "name": name,
                    "layer": layer,
                    "x": lane_x[layer],
                    "y": y,
                    "fmt": "parquet",
                }
            )
    return nodes, node_ids


def _lineage_graph_from_config(eng: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build lineage nodes + edges from pipeline config (fallback when no recorded events)."""
    cfg = eng.config
    sources = list((cfg.data.sources or {}).keys())
    by_layer: dict[str, list[str]] = {"source": sources, "bronze": [], "silver": [], "gold": []}

    for p_name, p_cfg in (cfg.data.pipelines or {}).items():
        dest = p_cfg.destination or p_name
        lay = _lineage_layer(p_name, p_cfg)
        if dest not in by_layer[lay]:
            by_layer[lay].append(dest)

    nodes, node_ids = _lineage_nodes(by_layer)

    edges: list[dict[str, Any]] = []
    for p_cfg in (cfg.data.pipelines or {}).values():
        src, dest = p_cfg.source, p_cfg.destination or ""
        if src in node_ids and dest in node_ids:
            edges.append({"src": node_ids[src], "dst": node_ids[dest]})

    return nodes, edges


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


def _pipeline_parquet_mtime(eng: Any, destination: str) -> str | None:
    """Return formatted mtime of the destination parquet if it exists in any layer."""
    dex_dir: Path = eng._dex_dir
    for layer in ("bronze", "silver", "gold"):
        p = dex_dir / "lakehouse" / layer / f"{destination}.parquet"
        if p.exists():
            mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
            return mtime.strftime("%b %d %H:%M")
    return None


def _pipeline_steps(cfg: Any) -> list[dict[str, str]]:
    """Extract transform steps from pipeline config into serialisable dicts."""
    raw = getattr(cfg, "steps", None) or getattr(cfg, "transforms", None) or []
    out: list[dict[str, str]] = []
    for s in raw:
        stype = str(getattr(s, "type", "transform"))
        cond = str(getattr(s, "condition", "") or "")
        sql = str(getattr(s, "sql", "") or "")
        key = getattr(s, "key", None)
        if cond:
            label = f"{stype}: {cond[:35]}…" if len(cond) > 35 else f"{stype}: {cond}"
        elif sql:
            first = sql.strip().splitlines()[0][:35]
            label = f"sql: {first}…" if len(sql.strip()) > 35 else f"sql: {first}"
        elif key:
            label = f"{stype}: {key}"
        else:
            label = stype
        out.append({"type": stype, "label": label})
    return out


def _build_pipeline_rows(eng: Any) -> list[dict[str, Any]]:
    rows = []
    for name, cfg in (eng.config.data.pipelines or {}).items():
        last = eng.pipeline_last_run(name)
        dest = str(cfg.destination or name)
        # Prefer event-store timestamp; fall back to parquet mtime for CLI runs
        last_run = fmt_ts(last.timestamp if last else None)
        if last_run == "—":
            last_run = _pipeline_parquet_mtime(eng, dest) or "—"
        rows.append(
            {
                "name": name,
                "schedule": fmt_cron(cfg.schedule or "") if cfg.schedule else "—",
                "status": _pipeline_status(last),
                "last_run": last_run,
                "duration_ms": f"{last.duration_ms:.0f}" if last and last.duration_ms else "—",
                "rows_in": str(last.rows_input) if last else "—",
                "rows_out": str(last.rows_output) if last else "—",
                "source": str(cfg.source or ""),
                "destination": dest,
                "steps": _pipeline_steps(cfg),
            }
        )
    return rows


def _serialize_run(r: Any) -> dict[str, Any]:
    """Serialise a single pipeline run record to a JSON-safe dict."""
    return {
        "run_id": r.run_id,
        "pipeline_name": r.pipeline_name,
        "timestamp": fmt_ts(r.timestamp),
        "success": r.success,
        "duration_ms": round(r.duration_ms, 0) if r.duration_ms else None,
        "rows_output": r.rows_output,
        "error": r.error or "",
    }


@router.get("/pipelines", response_class=HTMLResponse)
async def pipelines(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    rows = _build_pipeline_rows(eng)
    pipeline_data = {
        r["name"]: {"source": r["source"], "destination": r["destination"], "steps": r["steps"]}
        for r in rows
    }
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "source_types": _SOURCE_TYPES,
        "pipeline_data_json": json.dumps(pipeline_data),
    }
    return render(request, "data/pipelines.html", ctx)


@router.get("/pipelines/runs/all")
async def pipeline_runs_all(request: Request) -> Any:
    """JSON — last 50 runs across all pipelines."""
    from fastapi.responses import JSONResponse

    if guard(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    eng = get_eng()
    runs = eng.store.get_pipeline_runs(None)[:50]
    return JSONResponse([_serialize_run(r) for r in runs])


@router.get("/pipelines/{name}/runs")
async def pipeline_runs_for(request: Request, name: str) -> Any:
    """JSON — last 20 runs for a single pipeline."""
    from fastapi.responses import JSONResponse

    if guard(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    eng = get_eng()
    runs = eng.store.get_pipeline_runs(name)[:20]
    return JSONResponse([_serialize_run(r) for r in runs])


@router.post("/pipelines/run/{name}")
async def run_pipeline(request: Request, name: str) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    # Fire and forget in thread pool — pipeline is CPU/IO-heavy.
    asyncio.get_running_loop().run_in_executor(None, eng.run_pipeline, name)
    flash(request, f"Pipeline '{name}' started — refresh in a moment for results.")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/add")
async def add_pipeline(
    request: Request,
    name: Annotated[str, Form()],
    source: Annotated[str, Form()] = "",
    schedule: Annotated[str, Form()] = "",
    destination: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().add_pipeline(name.strip(), source.strip(), schedule.strip(), destination.strip())
        flash(request, f"Pipeline '{name}' added.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/delete/{name}")
async def delete_pipeline(request: Request, name: str) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().delete_pipeline(name)
        flash(request, f"Pipeline '{name}' deleted.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/{name}/schedule")
async def update_schedule(
    request: Request,
    name: str,
    schedule: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().update_pipeline_schedule(name, schedule.strip() or None)
        flash(request, f"Schedule updated for '{name}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/pipelines/{name}", status_code=303)


@router.get("/pipelines/{name}", response_class=HTMLResponse)
async def pipeline_detail(request: Request, name: str) -> HTMLResponse:
    if redir := guard(request):
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
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    rows = _build_source_rows(eng)
    flash_msg = request.session.pop("flash", None)
    ctx = base_ctx(request) | {
        "sources": rows,
        "source_types": _SOURCE_TYPES,
        "flash": flash_msg,
    }
    return render(request, "data/sources.html", ctx)


@router.get("/sources/{name}", response_class=HTMLResponse)
async def source_detail(request: Request, name: str) -> HTMLResponse:
    if redir := guard(request):
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


def _source_connection(
    type_: str,
    spark_master: str,
    spark_format: str,
    dbt_project_dir: str,
    dbt_model: str,
    dbt_target: str,
) -> dict[str, Any] | None:
    if type_ == "spark":
        conn = {k: v for k, v in {"master": spark_master, "format": spark_format}.items() if v}
        return conn or None
    if type_ == "dbt":
        conn = {
            k: v
            for k, v in {
                "project_dir": dbt_project_dir,
                "model": dbt_model,
                "target": dbt_target,
            }.items()
            if v
        }
        return conn or None
    return None


@router.post("/sources/add")
async def add_source(
    request: Request,
    name: Annotated[str, Form()],
    type_: Annotated[str, Form(alias="type")],
    path: Annotated[str, Form()] = "",
    spark_master: Annotated[str, Form()] = "",
    spark_format: Annotated[str, Form()] = "",
    dbt_project_dir: Annotated[str, Form()] = "",
    dbt_model: Annotated[str, Form()] = "",
    dbt_target: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        t = type_.strip()
        connection = _source_connection(
            t,
            spark_master.strip(),
            spark_format.strip(),
            dbt_project_dir.strip(),
            dbt_model.strip(),
            dbt_target.strip(),
        )
        get_eng().add_source(name.strip(), t, path.strip(), connection=connection)
        flash(request, f"Source '{name}' added.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/sources", status_code=303)


@router.post("/sources/delete/{name}")
async def delete_source(request: Request, name: str) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().delete_source(name)
        flash(request, f"Source '{name}' removed.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/sources", status_code=303)


# ── SQL Console ───────────────────────────────────────────────────────────────


_DEFAULT_SQL = (
    "SELECT table_name, table_schema, estimated_size\n"
    "FROM information_schema.tables\n"
    "ORDER BY table_schema, table_name\n"
    "LIMIT 50;"
)

# Matches the start of any statement that writes, loads external data, or
# escapes the lakehouse sandbox. Checked before execution.
_UNSAFE_SQL = re.compile(
    r"""
    ^\s*
    (
        INSERT | UPDATE | DELETE | MERGE |       # DML
        CREATE | DROP   | ALTER  | TRUNCATE |    # DDL
        ATTACH | DETACH |                      # multi-file access
        COPY   | EXPORT | IMPORT |             # file I/O
        LOAD   | INSTALL |                     # extension loading
        PRAGMA                                   # internals
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# read_* functions can reference arbitrary paths outside the lakehouse
_UNSAFE_FUNCTIONS = re.compile(
    r"\bread_(csv|parquet|json|ndjson|text|xml|avro|orc|feather|arrow)\s*\(",
    re.IGNORECASE,
)


def _validate_sql(query: str) -> str | None:
    """Return an error string if query is not allowed, else None."""
    stripped = query.strip()
    if not stripped:
        return "Query is empty."
    if _UNSAFE_SQL.match(stripped):
        return (
            "Only SELECT queries are allowed in the SQL console. "
            "DML, DDL, ATTACH, COPY, LOAD and INSTALL are disabled."
        )
    if _UNSAFE_FUNCTIONS.search(stripped):
        return (
            "Direct read_*() calls are disabled. "
            "Query the pre-registered table views instead (listed in the sidebar)."
        )
    return None


@router.get("/sql", response_class=HTMLResponse)
async def sql_console(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    catalog_entries: list[dict[str, Any]] = []
    for layer in ("bronze", "silver", "gold"):
        for tbl in eng.warehouse_tables(layer):
            schema = eng.warehouse_table_schema(tbl["name"], layer) or []
            catalog_entries.append(
                {"name": tbl["name"], "layer": layer, "column_count": len(schema)}
            )
    ctx = base_ctx(request) | {
        "sql_results": [],
        "sql_columns": [],
        "exec_ms": None,
        "catalog_entries": catalog_entries,
        "default_sql": _DEFAULT_SQL,
    }
    return render(request, "data/sql.html", ctx)


def _run_sql(
    lakehouse: Path, query: str
) -> tuple[list[str], list[dict[str, Any]], float | None, str]:
    """Execute *query* against lakehouse views. Returns (columns, rows, exec_ms, error)."""
    columns: list[str] = []
    results: list[dict[str, Any]] = []
    exec_ms: float | None = None
    try:
        t0 = time.monotonic()
        with duckdb.connect(":memory:") as conn:
            for layer in ("bronze", "silver", "gold"):
                layer_path = lakehouse / layer
                if layer_path.exists():
                    for pf in sorted(layer_path.glob("*.parquet")):
                        safe = str(pf.resolve())
                        with contextlib.suppress(Exception):
                            conn.execute(
                                f"CREATE VIEW IF NOT EXISTS {pf.stem} AS"
                                f" SELECT * FROM read_parquet('{safe}')"
                            )
                            conn.execute(
                                f"CREATE VIEW IF NOT EXISTS {layer}_{pf.stem} AS"
                                f" SELECT * FROM read_parquet('{safe}')"
                            )
            cursor = conn.execute(query)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                results = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        exec_ms = (time.monotonic() - t0) * 1000
    except Exception as exc:
        return [], [], None, str(exc)
    return columns, results, exec_ms, ""


@router.post("/sql/execute", response_class=HTMLResponse)
async def execute_sql(
    request: Request,
    query: Annotated[str, Form()],
) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]

    error = _validate_sql(query) or ""
    columns: list[str] = []
    results: list[dict[str, Any]] = []
    exec_ms: float | None = None

    if not error:
        eng = get_eng()
        lakehouse = eng.project_dir / ".dex" / "lakehouse"
        columns, results, exec_ms, error = _run_sql(lakehouse, query)

    # Build catalog sidebar entries (needed when rendering the full sql.html page)
    catalog_entries: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        eng = get_eng()
        for _layer in ("bronze", "silver", "gold"):
            for _tbl in eng.warehouse_tables(_layer):
                _schema = eng.warehouse_table_schema(_tbl["name"], _layer) or []
                catalog_entries.append(
                    {"name": _tbl["name"], "layer": _layer, "column_count": len(_schema)}
                )

    ctx = base_ctx(request) | {
        "query": query,
        "sql_results": results,
        "sql_columns": columns,
        "error": error,
        "exec_ms": exec_ms,
        "catalog_entries": catalog_entries,
        "default_sql": query,
    }
    if request.headers.get("HX-Request"):
        return render(request, "data/sql_results.html", ctx)
    return render(request, "data/sql.html", ctx)


# ── Lakehouse (all layers: Bronze · Silver · Gold) ────────────────────────────


@router.get("/lakehouse", response_class=HTMLResponse)
async def lakehouse(request: Request, layer: str = "") -> HTMLResponse:
    if redir := guard(request):
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
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {"tables": tables, "active_layer": layer}
    return render(request, "data/warehouse_tables.html", ctx)


# ── Warehouse (Gold layer — BI-ready structured data) ─────────────────────────


@router.get("/warehouse", response_class=HTMLResponse)
async def warehouse(request: Request) -> HTMLResponse:
    if redir := guard(request):
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
    if redir := guard(request):
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
    if redir := guard(request):
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
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    all_events = _get_lineage_events(eng, pipeline)
    pipeline_names = sorted({e["pipeline_name"] for e in all_events if e["pipeline_name"]})
    lin_nodes, lin_edges = _lineage_graph_from_config(eng)
    ctx = base_ctx(request) | {
        "events": all_events,
        "pipeline_names": pipeline_names,
        "filter_pipeline": pipeline,
        "view": view,
        "lineage_nodes": lin_nodes,
        "lineage_edges": lin_edges,
        "mermaid_diagram": _build_mermaid(all_events) if all_events else "",
    }
    return render(request, "data/lineage.html", ctx)


# ── Data Quality ──────────────────────────────────────────────────────────────


@router.get("/quality", response_class=HTMLResponse)
async def quality(request: Request) -> HTMLResponse:
    if redir := guard(request):
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
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        get_eng().quality_check_all_tables()
        flash(request, "Quality checks complete.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/quality", status_code=303)


# ── Catalog (alias for sources) ───────────────────────────────────────────────


@router.get("/catalog", response_class=HTMLResponse)
async def catalog(request: Request) -> HTMLResponse:
    if redir := guard(request):
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
                    "format": "parquet",
                }
            )
    ctx = base_ctx(request) | {"entries": entries, "active_tab": "data"}
    return render(request, "data/catalog.html", ctx)


@router.get("/catalog/{table_name}", response_class=HTMLResponse)
async def catalog_detail(request: Request, table_name: str) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    # Find the layer this table lives in
    found_layer: str | None = None
    found_path: str | None = None
    for layer in ("bronze", "silver", "gold"):
        for tbl in eng.warehouse_tables(layer):
            if tbl["name"] == table_name:
                found_layer = layer
                found_path = tbl.get("path")
                break
        if found_layer:
            break
    if not found_layer or not found_path:
        from fastapi.responses import Response

        return Response(status_code=404)  # type: ignore[return-value]
    schema = eng.warehouse_table_schema(table_name, found_layer) or []
    stats = eng.warehouse_table_stats(table_name, found_layer)
    lineage = eng.warehouse_table_lineage(table_name, found_layer)
    # Preview rows (first 8)
    preview_cols: list[str] = []
    preview_rows: list[list[Any]] = []
    with contextlib.suppress(Exception), duckdb.connect() as conn:
        rel = conn.execute(f"SELECT * FROM read_parquet('{found_path}') LIMIT 8")
        preview_cols = [d[0] for d in (rel.description or [])]
        preview_rows = [list(r) for r in rel.fetchall()]
    size_bytes = stats.get("size_bytes", 0)
    size_fmt = (
        f"{size_bytes / 1_048_576:.1f} MB"
        if size_bytes >= 1_048_576
        else f"{size_bytes / 1024:.1f} KB"
    )
    ctx = base_ctx(request) | {
        "active_tab": "data",
        "table_name": table_name,
        "layer": found_layer,
        "schema": schema,
        "row_count": stats.get("row_count", "—"),
        "column_count": stats.get("column_count", len(schema)),
        "size": size_fmt,
        "upstream": lineage.get("upstream", []),
        "downstream": lineage.get("downstream", []),
        "preview_cols": preview_cols,
        "preview_rows": preview_rows,
    }
    return render(request, "data/catalog_detail.html", ctx)


# ── Transforms ───────────────────────────────────────────────────────────────


@router.get("/transforms", response_class=HTMLResponse)
async def transforms(request: Request, pipeline: str = "") -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    rows = _build_pipeline_rows(eng)
    if not pipeline and rows:
        pipeline = rows[0]["name"]
    cfg = (eng.config.data.pipelines or {}).get(pipeline) if pipeline else None
    steps: list[dict[str, str]] = []
    if cfg:
        raw = getattr(cfg, "steps", None) or getattr(cfg, "transforms", None) or []
        for s in raw:
            sql = getattr(s, "sql", "") or ""
            if sql:
                steps.append({"type": str(getattr(s, "type", "sql")), "sql": sql.strip()})
    schedule_str = fmt_cron(cfg.schedule) if cfg and getattr(cfg, "schedule", None) else "—"
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "selected_pipeline": pipeline,
        "steps": steps,
        "schedule": schedule_str,
        "source": str(getattr(cfg, "source", "") or "") if cfg else "",
        "destination": str(getattr(cfg, "destination", "") or "") if cfg else "",
        "active_tab": "data",
    }
    return render(request, "data/transforms.html", ctx)


# ── Streaming ─────────────────────────────────────────────────────────────────

_STREAMING_TYPES = frozenset(
    {"kafka", "kinesis", "pubsub", "stream", "rabbitmq", "eventhub", "redpanda"}
)


@router.get("/streaming", response_class=HTMLResponse)
async def streaming(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    topics = [
        {
            "name": name,
            "type": str(getattr(cfg, "type", "")),
            "path": str(getattr(cfg, "path", None) or getattr(cfg, "broker", None) or ""),
            "status": "active",
        }
        for name, cfg in (eng.config.data.sources or {}).items()
        if str(getattr(cfg, "type", "")).lower() in _STREAMING_TYPES
    ]
    ctx = base_ctx(request) | {
        "topics": topics,
        "active_tab": "data",
    }
    return render(request, "data/streaming.html", ctx)


# ── Asset Graph / Contracts / Templates (stubs) ───────────────────────────────

_DATA_STUB_TITLES = {
    "/data/asset-graph": "Asset Graph",
    "/data/contracts": "Data Contracts",
    "/data/templates": "Pipeline Templates",
}


@router.get("/asset-graph", response_class=HTMLResponse)
@router.get("/contracts", response_class=HTMLResponse)
@router.get("/templates", response_class=HTMLResponse)
async def data_stub(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    return stub_page(request, _DATA_STUB_TITLES)
