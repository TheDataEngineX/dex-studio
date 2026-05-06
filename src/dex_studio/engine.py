"""DexEngine — direct dataenginex library access, no HTTP."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC
from pathlib import Path
from typing import Any

import duckdb
import structlog
import yaml
from dataenginex.config import load_config, validate_config
from dataenginex.config.schema import DexConfig
from dataenginex.data.pipeline.run_history import PipelineRunHistory
from dataenginex.data.pipeline.runner import PipelineResult, PipelineRunner
from dataenginex.data.quality.gates import ColumnSpec, check_quality
from dataenginex.ml.registry import ModelRegistry
from dataenginex.warehouse.lineage import PersistentLineage

from dex_studio.audit import AuditLogger

logger = structlog.getLogger()

__all__ = ["DexEngine"]


class DexEngine:
    """Local dataenginex engine — direct library access, no HTTP.

    Args:
        config_path: Path to a dex YAML config file.
    """

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).resolve()
        if not self.config_path.exists():
            msg = f"Config file not found: {self.config_path}"
            raise FileNotFoundError(msg)

        self.config: DexConfig = load_config(self.config_path)
        validate_config(self.config)

        self.project_dir = self.config_path.parent
        self._dex_dir = self.project_dir / ".dex"
        self._dex_dir.mkdir(parents=True, exist_ok=True)

        self.lineage = PersistentLineage(self._dex_dir / "lineage.json")
        self.pipeline_runner = PipelineRunner(
            self.config,
            data_dir=self._dex_dir / "lakehouse",
            project_dir=self.project_dir,
            lineage=self.lineage,
        )
        self.run_history = PipelineRunHistory(self._dex_dir / "pipeline_runs.json")
        self.audit = AuditLogger(self._dex_dir / "audit.json")
        self._duckdb_conn: Any = None

        # ML backends (graceful degradation)
        self.tracker: Any = self._init_ml_tracker()
        self.feature_store: Any = self._init_ml_feature_store()
        self.model_registry = ModelRegistry(
            persist_path=str(self._dex_dir / "models" / "registry.json"),
        )
        self.serving_engine: Any = self._init_ml_serving()

        # AI backends (graceful degradation)
        self.llm: Any = None
        self.agents: dict[str, Any] = {}
        self._init_ai()

        # AI layer — memory, observability, routing, runtime, sandbox
        self.ai_memory: Any = None
        self.ai_long_memory: Any = None
        self.ai_episodic: Any = None
        self.ai_audit: Any = None
        self.ai_cost: Any = None
        self.ai_metrics: Any = None
        self.checkpoint_mgr: Any = None
        self.sandbox: Any = None
        self.model_router: Any = None
        self._init_ai_layer()

        logger.info(
            "DexEngine ready",
            project=self.config.project.name,
            config=str(self.config_path),
        )

    # -- pipeline helpers ------------------------------------------------

    def run_pipeline(self, name: str) -> PipelineResult:
        """Run a pipeline and record the result in history."""
        import time

        start = time.monotonic()
        result = self.pipeline_runner.run(name)
        duration_ms = (time.monotonic() - start) * 1000
        self.run_history.record(result, duration_ms)

        self.audit.log(
            action="pipeline_run",
            resource=name,
            resource_type="pipeline",
            status="success" if result.success else "failure",
            details={
                "rows_input": result.rows_input,
                "rows_output": result.rows_output,
                "duration_ms": duration_ms,
                "error": result.error,
            },
        )
        return result

    def pipeline_stats(self) -> dict[str, int]:
        """Return summary stats for all pipelines."""
        pipelines = self.config.data.pipelines or {}
        total = len(pipelines)
        scheduled = sum(1 for p in pipelines.values() if p.schedule)
        failed = 0
        for name in pipelines:
            last = self.pipeline_last_run(name)
            if last is not None and not last.success:
                failed += 1
        return {"total": total, "scheduled": scheduled, "failed": failed, "running": 0}

    def pipeline_last_run(self, name: str) -> Any | None:
        """Return the most recent PipelineRunRecord for a pipeline, or None."""
        runs = self.run_history.get_runs(name)
        return runs[0] if runs else None

    def update_pipeline_schedule(self, name: str, schedule: str | None) -> None:
        """Update a pipeline's schedule and persist to disk."""
        if name not in self.config.data.pipelines:
            raise KeyError(f"Pipeline '{name}' not found")
        self.config.data.pipelines[name].schedule = schedule
        self._save_config()

    def _save_config(self) -> None:
        """Save the current config to disk as YAML."""
        dump = self.config.model_dump()
        with open(self.config_path, "w") as f:
            yaml.dump(dump, f, default_flow_style=False, sort_keys=False)

    @contextlib.contextmanager
    def _duckdb(self) -> Iterator[Any]:
        """Yield a persistent DuckDB connection for quality checks."""
        if self._duckdb_conn is None:
            self._duckdb_conn = duckdb.connect(database=":memory:")
        yield self._duckdb_conn

    def quality_check_table(self, table_name: str) -> dict[str, Any] | None:
        """Run quality checks on a warehouse table and return results."""
        layer, _, tbl = table_name.partition(".")
        if not layer or not tbl:
            return None
        table_path = self._dex_dir / "lakehouse" / layer / f"{tbl}.parquet"
        if not table_path.exists():
            return None
        try:
            with self._duckdb() as conn:
                conn.execute(f"CREATE VIEW IF NOT EXISTS qc_table AS SELECT * FROM '{table_path}'")
                col_result = conn.execute("DESCRIBE qc_table").fetchall()
                column_names = [row[0] for row in col_result]
                column_specs = [
                    ColumnSpec(name=row[0], dtype=row[1], nullable=True) for row in col_result
                ]
                result = check_quality(
                    conn,
                    "qc_table",
                    completeness=0.0,
                    uniqueness=column_names,
                    schema=column_specs,
                )
                conn.execute("DROP VIEW IF EXISTS qc_table")
                score = (
                    result.completeness_score * 0.4
                    + result.uniqueness_score * 0.3
                    + (1.0 if result.custom_passed else 0.0) * 0.3
                )
                return {
                    "score": score,
                    "completeness": result.completeness_score,
                    "uniqueness": result.uniqueness_score,
                    "custom_passed": result.custom_passed,
                    "schema_violations": result.schema_violations,
                    "passed": result.passed,
                    "details": result.details,
                }
        except Exception as exc:
            logger.warning("Quality check failed for %s: %s", table_name, exc)
            return None

    def quality_check_all_tables(self) -> dict[str, Any]:
        """Run quality checks on all warehouse tables."""
        import uuid
        from datetime import datetime

        results: dict[str, Any] = {}
        for layer in ("bronze", "silver", "gold"):
            tables = self.warehouse_tables(layer)
            for table in tables:
                full_name = f"{layer}.{table['name']}"
                result = self.quality_check_table(full_name)
                results[full_name] = result
        run_record = {
            "run_id": uuid.uuid4().hex[:8],
            "timestamp": datetime.now(UTC).isoformat(),
            "results": results,
        }
        history = self.quality_history()
        history["runs"].insert(0, run_record)
        history["runs"] = history["runs"][:50]
        self._save_quality_history(history)
        return results

    def quality_history(self) -> dict[str, Any]:
        """Load quality check history from disk."""
        import json

        history_file = self._dex_dir / "quality_history.json"
        if history_file.exists():
            try:
                data: dict[str, Any] = json.loads(history_file.read_text())
                return data
            except Exception:
                pass
        return {"runs": []}

    def _save_quality_history(self, history: dict[str, Any]) -> None:
        """Save quality check history to disk."""
        import json

        history_file = self._dex_dir / "quality_history.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(history, indent=2))

    # -- warehouse helpers -----------------------------------------------

    def warehouse_layers(self) -> list[dict[str, Any]]:
        """List medallion layers and table counts from .dex/lakehouse/."""
        lakehouse = self._dex_dir / "lakehouse"
        layers: list[dict[str, Any]] = []
        for layer_name in ("bronze", "silver", "gold"):
            layer_path = lakehouse / layer_name
            table_count = len(list(layer_path.glob("*.parquet"))) if layer_path.exists() else 0
            layers.append({"name": layer_name, "table_count": table_count})
        return layers

    def warehouse_tables(self, layer: str) -> list[dict[str, Any]]:
        """List parquet tables in a specific medallion layer."""
        layer_path = self._dex_dir / "lakehouse" / layer
        if not layer_path.exists():
            return []
        tables: list[dict[str, Any]] = []
        for f in layer_path.glob("*.parquet"):
            try:
                tables.append(
                    {
                        "name": f.stem,
                        "path": str(f),
                        "size_bytes": f.stat().st_size,
                    }
                )
            except OSError:
                continue
        return tables

    def warehouse_table_schema(self, table_name: str, layer: str) -> list[dict[str, Any]]:
        """Get column schema for a warehouse table."""
        table_path = self._dex_dir / "lakehouse" / layer / f"{table_name}.parquet"
        if not table_path.exists():
            return []
        try:
            with self._duckdb() as conn:
                conn.execute(f"CREATE VIEW IF NOT EXISTS wts AS SELECT * FROM '{table_path}'")
                cols = conn.execute("DESCRIBE wts").fetchall()
                conn.execute("DROP VIEW IF EXISTS wts")
                return [
                    {"name": row[0], "dtype": row[1], "nullable": row[2] == "YES"} for row in cols
                ]
        except Exception as exc:
            logger.warning("Failed to get schema for %s.%s: %s", layer, table_name, exc)
            return []

    def warehouse_table_stats(self, table_name: str, layer: str) -> dict[str, Any]:
        """Get stats for a warehouse table."""
        table_path = self._dex_dir / "lakehouse" / layer / f"{table_name}.parquet"
        if not table_path.exists():
            return {}
        size = table_path.stat().st_size
        schema = self.warehouse_table_schema(table_name, layer)
        row_count = None
        try:
            with self._duckdb() as conn:
                row_count = conn.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{table_path}')"
                ).fetchone()[0]
        except Exception:
            pass
        return {
            "size_bytes": size,
            "column_count": len(schema),
            "row_count": row_count,
        }

    def warehouse_table_lineage(self, table_name: str, layer: str) -> dict[str, Any]:
        """Get upstream and downstream lineage for a table."""
        upstream: list[dict[str, Any]] = []
        downstream: list[dict[str, Any]] = []
        if self.lineage is None:
            return {"upstream": upstream, "downstream": downstream}
        for ev in self.lineage.all_events:
            if ev.destination == table_name and ev.layer == layer and ev.parent_id:
                parent = self.lineage.get_event(ev.parent_id)
                if parent:
                    upstream.append(
                        {
                            "name": parent.destination,
                            "layer": parent.layer,
                            "event_id": parent.event_id,
                        }
                    )
            if ev.source == table_name and ev.layer == layer:
                children = self.lineage.get_children(ev.event_id)
                for child in children:
                    downstream.append(
                        {
                            "name": child.destination,
                            "layer": child.layer,
                            "event_id": child.event_id,
                        }
                    )
        return {"upstream": upstream, "downstream": downstream}

    # -- source query helpers -----------------------------------------------

    def _source_read_function(self, source_name: str) -> str | None:
        """Return the DuckDB read function name for a source, or None if unsupported."""
        sources = self.config.data.sources
        if source_name not in sources:
            return None
        src = sources[source_name]
        src_type = getattr(src, "type", None)
        if src_type is None:
            return None
        type_map = {
            "csv": "read_csv_auto",
            "parquet": "read_parquet",
            "json": "read_json_auto",
            "jsonl": "read_ndjson_auto",
        }
        type_str = src_type.value if hasattr(src_type, "value") else str(src_type)
        return type_map.get(type_str)

    def _get_source_path(self, source_name: str) -> tuple[Any, Path] | None:
        """Return (src, resolved_path) for a source, or None if not found/unresolvable."""
        src = self.config.data.sources.get(source_name)
        if src is None:
            return None
        path = getattr(src, "path", None) or getattr(src, "uri", None)
        if not path:
            return None
        return src, Path(path).resolve()

    def source_row_count(self, source_name: str) -> int | None:
        """Return row count for a source, or None on error."""
        result = self._get_source_path(source_name)
        if result is None:
            return None
        src, resolved = result
        read_fn = self._source_read_function(source_name)
        if read_fn is None:
            return None
        try:
            with duckdb.connect(":memory:") as conn:
                query_result = conn.execute(
                    f"SELECT COUNT(*) FROM {read_fn}('{resolved}')"
                ).fetchone()
            return query_result[0] if query_result else 0
        except Exception:
            return None

    def source_schema(self, source_name: str) -> list[dict[str, Any]] | None:
        """Return column schema for a source, or None on error."""
        result = self._get_source_path(source_name)
        if result is None:
            return None
        read_fn = self._source_read_function(source_name)
        if read_fn is None:
            return None
        _, resolved = result
        try:
            with duckdb.connect(":memory:") as conn:
                schema_rows = conn.execute(
                    f"DESCRIBE SELECT * FROM {read_fn}('{resolved}') LIMIT 1"
                ).fetchall()
            return [
                {
                    "column_name": row[0],
                    "column_type": row[1],
                    "nullable": row[3] == "YES",
                }
                for row in schema_rows
            ]
        except Exception:
            return None

    def source_sample(
        self,
        source_name: str,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]] | None:
        """Return sample rows from a source, or None on error."""
        result = self._get_source_path(source_name)
        if result is None:
            return None
        read_fn = self._source_read_function(source_name)
        if read_fn is None:
            return None
        _, resolved = result
        try:
            with duckdb.connect(":memory:") as conn:
                cursor = conn.execute(
                    f"SELECT * FROM {read_fn}('{resolved}') LIMIT {limit} OFFSET {offset}"
                )
                col_names = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
            return [dict(zip(col_names, row, strict=True)) for row in rows]
        except Exception:
            return None

    def source_stats(self, source_name: str) -> dict[str, Any] | None:
        """Return metadata for a source: row_count, column_count, size_bytes, path."""
        result = self._get_source_path(source_name)
        if result is None:
            return None
        src, resolved = result
        size_bytes = resolved.stat().st_size if resolved.exists() else 0
        schema = self.source_schema(source_name)
        return {
            "row_count": self.source_row_count(source_name),
            "column_count": len(schema) if schema else None,
            "size_bytes": size_bytes,
            "path": str(resolved),
            "connector_type": getattr(src, "type", "unknown"),
        }

    # -- health ----------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return component health summary."""
        return {
            "status": "healthy",
            "project": self.config.project.name,
            "components": {
                "pipeline_runner": self.pipeline_runner is not None,
                "lineage": self.lineage is not None,
                "tracker": self.tracker is not None,
                "feature_store": self.feature_store is not None,
                "model_registry": self.model_registry is not None,
                "serving_engine": self.serving_engine is not None,
                "llm": self.llm is not None,
                "agents": len(self.agents),
                "ai_memory": self.ai_memory is not None,
                "ai_audit": self.ai_audit is not None,
                "sandbox": self.sandbox is not None,
                "model_router": self.model_router is not None,
            },
        }

    # -- cleanup ---------------------------------------------------------

    def close(self) -> None:
        """Cleanup resources."""
        if (
            hasattr(self, "feature_store")
            and self.feature_store
            and hasattr(self.feature_store, "close")
        ):
            self.feature_store.close()
        logger.info("DexEngine shutdown")

    # -- private init helpers --------------------------------------------

    def _init_ml_tracker(self) -> Any:
        try:
            import dataenginex.ml.tracking.builtin  # noqa: F401
            from dataenginex.ml.tracking import tracker_registry

            tracker_cls = tracker_registry.get(self.config.ml.tracking.backend)
            return tracker_cls()
        except Exception:
            logger.warning("tracker init failed, ML tracking unavailable")
            return None

    def _init_ml_feature_store(self) -> Any:
        try:
            import dataenginex.ml.features.builtin  # noqa: F401
            from dataenginex.ml.features import feature_store_registry

            fs_cls = feature_store_registry.get(
                self.config.ml.features.backend,
            )
            return fs_cls(**self.config.ml.features.options)
        except Exception:
            logger.warning("feature store init failed, ML features unavailable")
            return None

    def _init_ml_serving(self) -> Any:
        try:
            from typing import cast

            import dataenginex.ml.serving_engine.builtin  # noqa: F401
            from dataenginex.ml.serving_engine import serving_registry

            serving_cls: Any = cast(
                Any,
                serving_registry.get(self.config.ml.serving.engine),
            )
            return serving_cls(
                model_registry=self.model_registry,
                model_dir=str(self._dex_dir / "models"),
            )
        except Exception:
            logger.warning("serving engine init failed, predictions unavailable")
            return None

    def _init_ai(self) -> None:
        """Initialize LLM provider and agents with graceful degradation."""
        try:
            from dataenginex.ml.llm import get_llm_provider

            self.llm = get_llm_provider(
                self.config.ai.llm.provider,
                model=self.config.ai.llm.model,
            )
        except Exception:
            self.llm = None
            logger.warning("LLM provider unavailable, agents disabled")

        if self.llm is None:
            return

        try:
            from typing import cast

            import dataenginex.ai.agents.builtin  # noqa: F401
            from dataenginex.ai.agents import agent_registry
            from dataenginex.ai.tools import tool_registry
            from dataenginex.ai.tools.builtin import register_builtin_tools

            register_builtin_tools()

            for name, agent_cfg in self.config.ai.agents.items():
                agent_llm = self.llm
                if agent_cfg.model:
                    try:
                        from dataenginex.ml.llm import (
                            get_llm_provider as _get,
                        )

                        agent_llm = _get(
                            self.config.ai.llm.provider,
                            model=agent_cfg.model,
                        )
                    except Exception:
                        pass
                agent_cls: Any = cast(
                    Any,
                    agent_registry.get(agent_cfg.runtime),
                )
                self.agents[name] = agent_cls(
                    llm=agent_llm,
                    system_prompt=agent_cfg.system_prompt,
                    tools=tool_registry,
                    max_iterations=agent_cfg.max_iterations,
                )
                logger.info("agent initialized", agent=name)
        except Exception:
            logger.warning("agent initialization failed")

    def _init_ai_layer(self) -> None:
        """Initialize AI layer: memory, observability, routing, runtime, sandbox."""
        try:
            from dataenginex.ai.memory.base import ShortTermMemory
            from dataenginex.ai.memory.episodic import EpisodicMemory
            from dataenginex.ai.memory.long_term import LongTermMemory
            from dataenginex.ai.observability.audit import AuditLog
            from dataenginex.ai.observability.cost import CostTracker
            from dataenginex.ai.observability.metrics import AgentMetrics
            from dataenginex.ai.runtime.checkpoint import CheckpointManager
            from dataenginex.ai.runtime.sandbox import Sandbox

            self.ai_memory = ShortTermMemory(max_entries=200)
            self.ai_long_memory = LongTermMemory()
            self.ai_episodic = EpisodicMemory()
            self.ai_audit = AuditLog()
            self.ai_cost = CostTracker()
            self.ai_metrics = AgentMetrics()
            self.checkpoint_mgr = CheckpointManager()
            self.sandbox = Sandbox()

            # Restore long-term memory from disk if it exists
            ltm_path = str(self._dex_dir / "ai_long_memory.json")
            if Path(ltm_path).exists():
                with contextlib.suppress(Exception):
                    self.ai_long_memory.load_from_file(ltm_path)

            self._init_model_router()
            logger.info("AI layer initialized")
        except Exception:
            logger.warning("AI layer init failed — memory/sandbox/routing unavailable")

    def _init_model_router(self) -> None:
        """Initialize ModelRouter with whichever providers are configured."""
        import os

        from dataenginex.ai.routing.router import ModelRouter

        providers: dict[str, Any] = {}

        if os.environ.get("ANTHROPIC_API_KEY"):
            from dataenginex.ai.routing.anthropic import AnthropicProvider

            providers["anthropic"] = AnthropicProvider()

        if os.environ.get("OPENAI_API_KEY"):
            from dataenginex.ai.routing.openai import OpenAIProvider

            providers["openai"] = OpenAIProvider()

        if os.environ.get("HF_TOKEN"):
            from dataenginex.ai.routing.huggingface import HuggingFaceProvider

            providers["huggingface"] = HuggingFaceProvider()
        else:
            # Default "simple" tier to local Ollama
            from dataenginex.ai.routing.ollama import OllamaProvider

            providers["huggingface"] = OllamaProvider()

        if providers:
            self.model_router = ModelRouter(providers)
            logger.info("ModelRouter initialized", providers=list(providers.keys()))
