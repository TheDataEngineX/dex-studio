"""DexEngine — direct dataenginex library access, no HTTP.

Replaces DexClient for local mode. Wraps all dataenginex backends
and exposes them to NiceGUI pages as typed Python objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from dataenginex.config import load_config, validate_config
from dataenginex.config.schema import DexConfig
from dataenginex.data.pipeline.run_history import PipelineRunHistory
from dataenginex.data.pipeline.runner import PipelineResult, PipelineRunner
from dataenginex.ml.registry import ModelRegistry
from dataenginex.warehouse.lineage import PersistentLineage

logger = structlog.get_logger()

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

        self.project_dir = self.config_path.parent
        self.config: DexConfig = load_config(self.config_path)
        validate_config(self.config)

        # Project directory structure
        self._dex_dir = self.project_dir / ".dex"
        self._dex_dir.mkdir(parents=True, exist_ok=True)

        # Data backends
        self.lineage = PersistentLineage(self._dex_dir / "lineage.json")
        self.pipeline_runner = PipelineRunner(
            self.config,
            data_dir=self._dex_dir / "lakehouse",
            project_dir=self.project_dir,
            lineage=self.lineage,
        )
        self.run_history = PipelineRunHistory(self._dex_dir / "pipeline_runs.json")

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
        return result

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
