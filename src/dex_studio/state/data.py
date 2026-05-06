"""Reflex state for data features — pipelines, sources, warehouse, SQL, lineage, quality."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

import duckdb
import reflex as rx

from dex_studio.state.base import BaseState


class PipelineState(BaseState):
    """State for pipeline management: listing, selecting, running, and viewing run history."""

    pipelines: list[dict[str, Any]] = []
    pipeline_running: str = ""
    pipeline_job_status: str = ""
    pipeline_last_result: dict[str, Any] = {}
    selected_pipeline: str = ""
    pipeline_detail: dict[str, Any] = {}
    pipeline_steps: list[dict[str, Any]] = []
    pipeline_history: list[dict[str, Any]] = []

    @rx.event
    async def select_pipeline(self, name: str) -> AsyncGenerator[None]:
        self.selected_pipeline = name
        self.pipeline_detail = {}
        self.pipeline_steps = []
        self.pipeline_history = []
        self.is_loading = True
        yield
        try:
            eng = self._engine()
            pipelines = eng.config.data.pipelines or {}
            cfg = pipelines.get(name)
            if cfg:
                steps = [
                    {
                        "type": s.type,
                        "condition": s.condition or "",
                        "sql": s.sql or "",
                        "expression": s.expression or "",
                        "name": s.name or "",
                    }
                    for s in (cfg.transforms or [])
                ]
                self.pipeline_detail = {
                    "name": name,
                    "source": cfg.source or "",
                    "destination": cfg.destination or "",
                    "schedule": cfg.schedule or "",
                    "depends_on": ", ".join(cfg.depends_on) if cfg.depends_on else "",
                }
                self.pipeline_steps = steps
            self.pipeline_history = [
                {**r.to_dict(), "error": r.error or ""} for r in eng.run_history.get_runs(name)
            ]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_pipelines(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            pipelines = eng.config.data.pipelines or {}
            rows = []
            for name, cfg in pipelines.items():
                last = eng.pipeline_last_run(name)
                rows.append(
                    {
                        "name": name,
                        "status": "failed" if last and not last.success else "idle",
                        "last_run": last.timestamp if last else "-",
                        "duration_ms": last.duration_ms if last else 0,
                        "schedule": cfg.schedule or "",
                    }
                )
            self.pipelines = rows
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def run_pipeline(self, name: str) -> AsyncGenerator[None]:
        self.pipeline_running = name
        self.pipeline_job_status = "running"
        yield
        try:
            eng = self._engine()
            result = await asyncio.to_thread(eng.run_pipeline, name)
            self.pipeline_job_status = "success" if result.success else "failed"
            self.pipeline_last_result = {
                "success": result.success,
                "rows_input": result.rows_input,
                "rows_output": result.rows_output,
                "error": result.error,
            }
            kind = "success" if result.success else "error"
            self._push_toast(f"Pipeline '{name}': {self.pipeline_job_status}", kind)
        except Exception as exc:
            self.pipeline_job_status = "failed"
            self._set_error(str(exc))
        finally:
            self.pipeline_running = ""


class SourceState(BaseState):
    """State for data sources: schema inspection, sample preview, and connection stats."""

    sources: list[dict[str, Any]] = []
    selected_source: str = ""
    source_detail: dict[str, Any] = {}
    source_schema_cols: list[dict[str, Any]] = []
    source_sample_rows: list[dict[str, Any]] = []
    source_sample_cols: list[str] = []

    @rx.event
    async def select_source(self, name: str) -> AsyncGenerator[None]:
        self.selected_source = name
        self.source_detail = {}
        self.source_schema_cols = []
        self.source_sample_rows = []
        self.source_sample_cols = []
        self.is_loading = True
        yield
        try:
            eng = self._engine()
            stats = eng.source_stats(name) or {}
            schema = eng.source_schema(name) or []
            sample = eng.source_sample(name, limit=10) or []
            size_bytes = stats.get("size_bytes") or 0
            self.source_detail = {
                "row_count": str(stats.get("row_count") or "—"),
                "column_count": str(stats.get("column_count") or "—"),
                "size_label": f"{size_bytes:,} B" if size_bytes else "—",
                "path": str(stats.get("path") or ""),
                "connector_type": str(stats.get("connector_type") or ""),
            }
            self.source_schema_cols = [
                {
                    "column_name": c.get("column_name", ""),
                    "column_type": c.get("column_type", ""),
                    "nullable": "yes" if c.get("nullable") else "no",
                }
                for c in schema
            ]
            if sample:
                self.source_sample_cols = list(sample[0].keys())
                self.source_sample_rows = [{k: str(v) for k, v in row.items()} for row in sample]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_sources(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            self.sources = [
                {
                    "name": name,
                    "type": str(getattr(src, "type", "unknown")),
                    "path": str(getattr(src, "path", "") or ""),
                    "status": "active",
                }
                for name, src in (eng.config.data.sources or {}).items()
            ]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False


class WarehouseState(BaseState):
    """State for the medallion warehouse: layer listing and per-layer table browsing."""

    warehouse_layers: list[dict[str, Any]] = []
    warehouse_tables: list[dict[str, Any]] = []
    active_layer: str = "bronze"

    @rx.event
    async def load_warehouse_layers(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            self.warehouse_layers = self._engine().warehouse_layers()
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_warehouse_tables(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            self.warehouse_tables = self._engine().warehouse_tables(self.active_layer)
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def set_active_layer(self, layer: str) -> AsyncGenerator[None]:
        self.active_layer = layer
        async for _ in self.load_warehouse_tables():  # type: ignore[attr-defined]
            yield


class SQLState(BaseState):
    """State for the in-browser DuckDB SQL console with query history."""

    sql_query: str = "SELECT 1"
    sql_results: list[dict[str, Any]] = []
    sql_columns: list[str] = []
    sql_error: str = ""
    sql_exec_ms: float = 0.0
    sql_history: list[str] = []

    @rx.event
    async def execute_sql(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.sql_error = ""
        self.sql_results = []
        self.sql_columns = []
        self.sql_exec_ms = 0.0
        yield
        query = self.sql_query
        t0 = time.monotonic()
        try:

            def _run() -> tuple[list[str], list[dict[str, Any]]]:
                with duckdb.connect(":memory:") as conn:
                    cursor = conn.execute(query)
                    cols = [d[0] for d in cursor.description] if cursor.description else []
                    rows = [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]
                    return cols, rows

            cols, rows = await asyncio.to_thread(_run)
            self.sql_exec_ms = round((time.monotonic() - t0) * 1000, 1)
            self.sql_columns = cols
            self.sql_results = rows
            self.sql_history = [query, *self.sql_history[:19]]
        except Exception as exc:
            self.sql_exec_ms = round((time.monotonic() - t0) * 1000, 1)
            self.sql_error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def set_sql_query(self, value: str) -> None:
        self.sql_query = value

    @rx.event
    def load_from_history(self, query: str) -> None:
        self.sql_query = query


class LineageState(BaseState):
    """State for data lineage: event list with per-pipeline filtering."""

    lineage_events: list[dict[str, Any]] = []
    lineage_filter_pipeline: str = ""

    @rx.event
    async def load_lineage(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            self.lineage_events = [e.to_dict() for e in eng.lineage.all_events]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    def set_lineage_filter(self, pipeline: str) -> None:
        self.lineage_filter_pipeline = pipeline

    @rx.var
    def filtered_events(self) -> list[dict[str, Any]]:
        if not self.lineage_filter_pipeline:
            return self.lineage_events
        return [
            e for e in self.lineage_events if e.get("pipeline_name") == self.lineage_filter_pipeline
        ]


class QualityState(BaseState):
    """State for data quality: aggregate score and per-table check results."""

    quality_score: float = 0.0
    quality_checks: list[dict[str, Any]] = []

    @rx.event
    async def load_quality(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            history = eng.quality_history()
            runs = history.get("runs", [])
            if runs:
                latest = runs[0].get("results", {})
                scores = [v["score"] for v in latest.values() if v and "score" in v]
                self.quality_score = round(sum(scores) / len(scores), 3) if scores else 0.0
                self.quality_checks = [
                    {
                        "table": k,
                        "name": k,
                        "status": "passed" if (v or {}).get("passed") else "failed",
                        **(v or {}),
                    }
                    for k, v in latest.items()
                ]
            else:
                self.quality_score = 0.0
                self.quality_checks = []
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False


class DataState(PipelineState):
    """Backwards-compatible alias — pages that import DataState still work."""

    sources: list[dict[str, Any]] = []
    warehouse_layers: list[dict[str, Any]] = []
    warehouse_tables: list[dict[str, Any]] = []
    active_layer: str = "bronze"
    sql_query: str = "SELECT 1"
    sql_results: list[dict[str, Any]] = []
    sql_columns: list[str] = []
    sql_error: str = ""
    sql_exec_ms: float = 0.0
    lineage_events: list[dict[str, Any]] = []
    quality_score: float = 0.0
    quality_checks: list[dict[str, Any]] = []

    @rx.event
    async def load_sources(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            self.sources = [
                {
                    "name": name,
                    "type": str(getattr(src, "type", "unknown")),
                    "path": str(getattr(src, "path", "") or ""),
                    "status": "active",
                }
                for name, src in (eng.config.data.sources or {}).items()
            ]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_warehouse_layers(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            self.warehouse_layers = self._engine().warehouse_layers()
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_lineage(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            self.lineage_events = [e.to_dict() for e in eng.lineage.all_events]
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_quality(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            history = eng.quality_history()
            runs = history.get("runs", [])
            if runs:
                latest = runs[0].get("results", {})
                scores = [v["score"] for v in latest.values() if v and "score" in v]
                self.quality_score = round(sum(scores) / len(scores), 3) if scores else 0.0
                self.quality_checks = [
                    {
                        "table": k,
                        "name": k,
                        "status": "passed" if (v or {}).get("passed") else "failed",
                        **(v or {}),
                    }
                    for k, v in latest.items()
                ]
            else:
                self.quality_score = 0.0
                self.quality_checks = []
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False
