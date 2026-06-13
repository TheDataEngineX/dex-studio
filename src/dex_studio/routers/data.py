"""Data domain routes — pipelines, sources, SQL, warehouse, lineage, quality."""

from __future__ import annotations

import contextlib
import datetime
import os
import re
import time
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio import _json
from dex_studio.flow import build_nodes
from dex_studio.jobs import run_pipeline_bg
from dex_studio.routers._deps import (
    JsonReadDep,
    ReadDep,
    WriteDep,
    base_ctx,
    flash,
    render,
    stub_page,
)
from dex_studio.utils import fmt_cron, fmt_ts

router = APIRouter()

_SOURCE_TYPES = [
    "csv",
    "parquet",
    "delta",
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
def data_dashboard(request: Request, eng: ReadDep) -> HTMLResponse:
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
def pipelines(request: Request, eng: ReadDep) -> HTMLResponse:
    rows = _build_pipeline_rows(eng)
    pipeline_data = {
        r["name"]: {"source": r["source"], "destination": r["destination"], "steps": r["steps"]}
        for r in rows
    }
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "source_types": _SOURCE_TYPES,
        "pipeline_data_json": _json.dumps(pipeline_data),
    }
    return render(request, "data/pipelines.html", ctx)


@router.get("/pipelines/runs/all")
def pipeline_runs_all(request: Request, eng: JsonReadDep) -> Any:
    """JSON — last 50 runs across all pipelines."""
    from fastapi.responses import JSONResponse

    runs = eng.store.get_pipeline_runs(None)[:50]
    return JSONResponse([_serialize_run(r) for r in runs])


@router.get("/pipelines/{name}/runs")
def pipeline_runs_for(request: Request, eng: JsonReadDep, name: str) -> Any:
    """JSON — last 20 runs for a single pipeline."""
    from fastapi.responses import JSONResponse

    runs = eng.store.get_pipeline_runs(name)[:20]
    return JSONResponse([_serialize_run(r) for r in runs])


@router.post("/pipelines/run/{name}")
def run_pipeline(request: Request, _: WriteDep, name: str) -> RedirectResponse:
    status = run_pipeline_bg(name)
    if status == "started":
        flash(request, f"Pipeline '{name}' started — refresh in a moment for results.")
    elif status == "running":
        flash(request, f"Pipeline '{name}' is already running.", "warning")
    elif status == "low_memory":
        flash(request, "Not enough memory to run a pipeline safely. Free up RAM first.", "error")
    else:
        flash(request, "System busy — too many pipelines queued. Try again shortly.", "warning")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/add")
def add_pipeline(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    source: Annotated[str, Form()] = "",
    schedule: Annotated[str, Form()] = "",
    destination: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        eng.add_pipeline(name.strip(), source.strip(), schedule.strip(), destination.strip())
        flash(request, f"Pipeline '{name}' added.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/delete/{name}")
def delete_pipeline(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    try:
        eng.delete_pipeline(name)
        flash(request, f"Pipeline '{name}' deleted.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/{name}/schedule")
def update_schedule(
    request: Request,
    eng: WriteDep,
    name: str,
    schedule: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        eng.update_pipeline_schedule(name, schedule.strip() or None)
        flash(request, f"Schedule updated for '{name}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/pipelines/{name}", status_code=303)


@router.get("/pipelines/{name}", response_class=HTMLResponse)
def pipeline_detail(request: Request, eng: ReadDep, name: str) -> HTMLResponse:
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
def sources(request: Request, eng: ReadDep) -> HTMLResponse:
    rows = _build_source_rows(eng)
    ctx = base_ctx(request) | {
        "sources": rows,
        "source_types": _SOURCE_TYPES,
    }
    return render(request, "data/sources.html", ctx)


@router.get("/sources/{name}", response_class=HTMLResponse)
def source_detail(request: Request, eng: ReadDep, name: str) -> HTMLResponse:
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
def add_source(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    type_: Annotated[str, Form(alias="type")],
    path: Annotated[str, Form()] = "",
    spark_master: Annotated[str, Form()] = "",
    spark_format: Annotated[str, Form()] = "",
    dbt_project_dir: Annotated[str, Form()] = "",
    dbt_model: Annotated[str, Form()] = "",
    dbt_target: Annotated[str, Form()] = "",
) -> RedirectResponse:
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
        eng.add_source(name.strip(), t, path.strip(), connection=connection)
        flash(request, f"Source '{name}' added.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/sources", status_code=303)


@router.post("/sources/delete/{name}")
def delete_source(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    try:
        eng.delete_source(name)
        flash(request, f"Source '{name}' removed.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/sources", status_code=303)


# ── SQL Console ───────────────────────────────────────────────────────────────


_DEFAULT_SQL = (
    "SELECT table_name, table_schema, table_type\n"
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

# DuckDB allows `FROM '/path/to/file'` as a shorthand for read_*() — block it.
_UNSAFE_LITERAL_FROM = re.compile(r"""\bFROM\s+['"]""", re.IGNORECASE)


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
    if _UNSAFE_LITERAL_FROM.search(stripped):
        return (
            "Literal file paths in FROM clauses are disabled. "
            "Query the pre-registered table views instead."
        )
    return None


@router.get("/sql", response_class=HTMLResponse)
def sql_console(request: Request, eng: ReadDep) -> HTMLResponse:
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
def execute_sql(
    request: Request,
    eng: WriteDep,
    query: Annotated[str, Form()],
) -> HTMLResponse:
    error = _validate_sql(query) or ""
    columns: list[str] = []
    results: list[dict[str, Any]] = []
    exec_ms: float | None = None

    if not error:
        lakehouse = eng.project_dir / ".dex" / "lakehouse"
        columns, results, exec_ms, error = _run_sql(lakehouse, query)

    # Build catalog sidebar entries (needed when rendering the full sql.html page)
    catalog_entries: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
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
def lakehouse(request: Request, eng: ReadDep, layer: str = "") -> HTMLResponse:
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
def lakehouse_tables_partial(request: Request, eng: ReadDep, layer: str = "bronze") -> HTMLResponse:
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {"tables": tables, "active_layer": layer}
    return render(request, "data/warehouse_tables.html", ctx)


# ── Warehouse (Gold layer — BI-ready structured data) ─────────────────────────


@router.get("/warehouse", response_class=HTMLResponse)
def warehouse(request: Request, eng: ReadDep) -> HTMLResponse:
    tables = eng.warehouse_tables("gold")
    ctx = base_ctx(request) | {
        "tables": tables,
        "active_layer": "gold",
    }
    return render(request, "data/warehouse.html", ctx)


@router.get("/warehouse/tables", response_class=HTMLResponse)
def warehouse_tables_partial(request: Request, eng: ReadDep, layer: str = "bronze") -> HTMLResponse:
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
def lineage_graph_partial(request: Request, eng: ReadDep, pipeline: str = "") -> HTMLResponse:
    events = _get_lineage_events(eng, pipeline)
    diagram = _build_mermaid(events) if events else ""
    if diagram:
        html = f'<pre class="mermaid" style="background:transparent;font-size:13px">{diagram}</pre>'
    else:
        html = '<p style="font-size:13px;color:var(--gray-9)">No graph data available.</p>'
    return HTMLResponse(html)


@router.get("/lineage", response_class=HTMLResponse)
def lineage(
    request: Request, eng: ReadDep, pipeline: str = "", view: str = "table"
) -> HTMLResponse:
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
def quality(request: Request, eng: ReadDep) -> HTMLResponse:
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
def run_quality(request: Request, eng: WriteDep) -> RedirectResponse:
    try:
        eng.quality_check_all_tables()
        flash(request, "Quality checks complete.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/quality", status_code=303)


@router.post("/quality/tests/add")
def add_quality_test(
    request: Request,
    eng: WriteDep,
    table: Annotated[str, Form()],
    test_type: Annotated[str, Form()],
    column: Annotated[str, Form()] = "",
    threshold: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        tests_path = eng.project_dir / ".dex" / "quality_tests.json"
        existing: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            existing = _json.loads(tests_path.read_text())
        existing.append(
            {
                "table": table,
                "test_type": test_type,
                "column": column,
                "threshold": threshold,
                "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )
        tests_path.parent.mkdir(parents=True, exist_ok=True)
        tests_path.write_text(_json.dumps(existing, indent=2))
        flash(request, f"Test '{test_type}' added for table '{table}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/quality", status_code=303)


@router.post("/catalog/register")
def catalog_register(
    request: Request,
    eng: WriteDep,
    table_name: Annotated[str, Form()],
    file_path: Annotated[str, Form()],
    layer: Annotated[str, Form()] = "bronze",
) -> RedirectResponse:
    try:
        import shutil

        project_root = eng.project_dir.resolve()
        src = Path(file_path.strip()).resolve()
        if not str(src).startswith(str(project_root) + "/"):
            flash(request, "File path must be within the project directory.", "error")
            return RedirectResponse("/data/catalog", status_code=303)
        if not src.exists():
            flash(request, f"File not found: {file_path}", "error")
            return RedirectResponse("/data/catalog", status_code=303)
        dest_dir = eng.project_dir / ".dex" / "lakehouse" / layer
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-z0-9_]", "_", table_name.strip().lower())
        dest = dest_dir / f"{safe_name}.parquet"
        if src.suffix.lower() == ".csv":
            duckdb.execute(
                "COPY (SELECT * FROM read_csv_auto(?)) TO ? (FORMAT PARQUET)",
                [str(src), str(dest)],
            )
        else:
            shutil.copy2(src, dest)
        flash(request, f"Table '{safe_name}' registered in {layer} layer.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/catalog", status_code=303)


# ── Catalog (alias for sources) ───────────────────────────────────────────────


@router.get("/catalog", response_class=HTMLResponse)
def catalog(request: Request, eng: ReadDep) -> HTMLResponse:
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
def catalog_detail(request: Request, eng: ReadDep, table_name: str) -> HTMLResponse:
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
def transforms(request: Request, eng: ReadDep, pipeline: str = "") -> HTMLResponse:
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
    all_steps: list[dict[str, str]] = []
    if cfg:
        for s in getattr(cfg, "transforms", None) or []:
            key = getattr(s, "key", None)
            key_str = ", ".join(key) if isinstance(key, list) else (key or "")
            detail = (
                getattr(s, "sql", None)
                or getattr(s, "condition", None)
                or getattr(s, "expression", None)
                or key_str
                or getattr(s, "name", None)
                or ""
            )
            all_steps.append(
                {"type": str(getattr(s, "type", "")), "detail": str(detail).strip()[:140]}
            )
    schedule_str = fmt_cron(cfg.schedule) if cfg and getattr(cfg, "schedule", None) else "—"
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "selected_pipeline": pipeline,
        "steps": steps,
        "all_steps": all_steps,
        "nodes": build_nodes(cfg),
        "transform_types": ["filter", "derive", "deduplicate", "sql"],
        "schedule": schedule_str,
        "source": str(getattr(cfg, "source", "") or "") if cfg else "",
        "destination": str(getattr(cfg, "destination", "") or "") if cfg else "",
        "active_tab": "data",
    }
    return render(request, "data/transforms.html", ctx)


@router.post("/transforms/{pipeline}/add")
def add_transform(
    request: Request,
    eng: WriteDep,
    pipeline: str,
    type_: Annotated[str, Form(alias="type")],
    condition: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    expression: Annotated[str, Form()] = "",
    key: Annotated[str, Form()] = "",
    sql: Annotated[str, Form()] = "",
) -> RedirectResponse:
    step: dict[str, Any] = {"type": type_.strip()}
    if condition.strip():
        step["condition"] = condition.strip()
    if name.strip():
        step["name"] = name.strip()
    if expression.strip():
        step["expression"] = expression.strip()
    if key.strip():
        keys = [k.strip() for k in key.split(",") if k.strip()]
        step["key"] = keys if len(keys) > 1 else keys[0]
    if sql.strip():
        step["sql"] = sql.strip()
    try:
        eng.add_pipeline_transform(pipeline, step)
        flash(request, f"Added {type_.strip()} step to '{pipeline}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/transforms?pipeline={pipeline}", status_code=303)


@router.post("/transforms/{pipeline}/delete/{index}")
def delete_transform(
    request: Request, eng: WriteDep, pipeline: str, index: int
) -> RedirectResponse:
    try:
        eng.delete_pipeline_transform(pipeline, index)
        flash(request, f"Removed step {index + 1} from '{pipeline}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/transforms?pipeline={pipeline}", status_code=303)


@router.get("/transforms/{pipeline}/preview", response_class=HTMLResponse)
def transform_flow_preview(request: Request, eng: ReadDep, pipeline: str) -> HTMLResponse:
    """HTMX partial — the flow canvas with real per-stage row counts (sampled)."""
    cfg = (eng.config.data.pipelines or {}).get(pipeline)
    if cfg is None:
        return HTMLResponse("")
    stages: list[Any] | None = None
    with contextlib.suppress(Exception):
        stages = eng.preview_flow(pipeline).get("stages")
    ctx = base_ctx(request) | {
        "nodes": build_nodes(cfg, stages),
        "selected_pipeline": pipeline,
        "auto_load": False,
    }
    return render(request, "data/flow_canvas.html", ctx)


@router.post("/transforms/{pipeline}/reorder/{index}/{direction}")
def reorder_transform(
    request: Request, eng: WriteDep, pipeline: str, index: int, direction: int
) -> RedirectResponse:
    try:
        eng.reorder_pipeline_transform(pipeline, index, 1 if direction > 0 else -1)
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/transforms?pipeline={pipeline}", status_code=303)


# ── Streaming ─────────────────────────────────────────────────────────────────

_STREAMING_TYPES = frozenset(
    {"kafka", "kinesis", "pubsub", "stream", "rabbitmq", "eventhub", "redpanda"}
)


@router.get("/streaming", response_class=HTMLResponse)
def streaming(request: Request, eng: ReadDep) -> HTMLResponse:
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
def data_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _DATA_STUB_TITLES)
