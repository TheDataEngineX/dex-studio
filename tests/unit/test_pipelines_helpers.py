"""Tests for DexEngine pipeline query helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from dataenginex.engine import DexEngine

from dex_studio.routers.data import _pipeline_graph_view, _pipeline_lineage_view
from dex_studio.studio_db import StudioDb


def test_pipeline_stats_returns_dict(engine: DexEngine) -> None:
    """pipeline_stats returns a dict with total, scheduled, failed, running."""
    stats = engine.pipeline_stats()
    assert isinstance(stats, dict)
    assert "total" in stats
    assert "scheduled" in stats
    assert "failed" in stats
    assert "running" in stats
    assert stats["total"] >= 0
    assert stats["scheduled"] >= 0
    assert stats["failed"] >= 0
    assert stats["running"] >= 0


def test_pipeline_stats_total_matches_config(engine: DexEngine) -> None:
    """pipeline_stats total equals number of pipelines in config."""
    stats = engine.pipeline_stats()
    expected = len(engine.config.data.pipelines)
    assert stats["total"] == expected


def test_pipeline_stats_scheduled_count(engine: DexEngine) -> None:
    """pipeline_stats scheduled equals count of pipelines with a schedule."""
    stats = engine.pipeline_stats()
    expected = sum(1 for p in engine.config.data.pipelines.values() if p.schedule)
    assert stats["scheduled"] == expected


def test_pipeline_last_run_returns_record_or_none(engine: DexEngine) -> None:
    """pipeline_last_run returns PipelineRunRecord or None."""
    pipelines = list(engine.config.data.pipelines.keys())
    if pipelines:
        result = engine.pipeline_last_run(pipelines[0])
        # Result is either None or has run_id, success, timestamp fields
        if result is not None:
            assert hasattr(result, "run_id")
            assert hasattr(result, "success")
            assert hasattr(result, "timestamp")


def test_pipeline_last_run_unknown_pipeline_returns_none(engine: DexEngine) -> None:
    """pipeline_last_run returns None for non-existent pipeline."""
    result = engine.pipeline_last_run("nonexistent_pipeline_xyz")
    assert result is None


def test_update_pipeline_schedule_changes_config(engine: DexEngine) -> None:
    """update_pipeline_schedule modifies the pipeline schedule in config."""
    pipelines = list(engine.config.data.pipelines.keys())
    if pipelines:
        name = pipelines[0]
        original = engine.config.data.pipelines[name].schedule
        engine.update_pipeline_schedule(name, "0 8 * * *")
        assert engine.config.data.pipelines[name].schedule == "0 8 * * *"
        # Restore original
        engine.update_pipeline_schedule(name, original)


def test_update_pipeline_schedule_saves_to_disk(engine: DexEngine, tmp_path: Path) -> None:
    """update_pipeline_schedule persists the schedule to the config file."""
    pipelines = list(engine.config.data.pipelines.keys())
    if pipelines:
        name = pipelines[0]
        engine.update_pipeline_schedule(name, "*/15 * * * *")
        # Re-load config from disk and verify
        from dataenginex.config import load_config

        reloaded = load_config(engine.config_path)
        assert reloaded.data.pipelines[name].schedule == "*/15 * * * *"


def test_update_pipeline_schedule_invalid_pipeline_raises(engine: DexEngine) -> None:
    """update_pipeline_schedule raises KeyError for non-existent pipeline."""
    with pytest.raises(KeyError):
        engine.update_pipeline_schedule("nonexistent_xyz", "0 8 * * *")


def _make_eng(
    pipelines: dict[str, SimpleNamespace], project_name: str = "default"
) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            data=SimpleNamespace(pipelines=pipelines),
            project=SimpleNamespace(name=project_name),
        )
    )


class TestSourceUsedBy:
    def test_finds_pipelines_using_source(self) -> None:
        from dex_studio.routers.data import _source_used_by

        cfg_a = SimpleNamespace(source="raw_orders")
        cfg_b = SimpleNamespace(source="raw_users")
        cfg_c = SimpleNamespace(source="raw_orders")
        eng = _make_eng({"clean_orders": cfg_a, "clean_users": cfg_b, "silver_orders": cfg_c})

        used_by = _source_used_by(eng, "raw_orders")

        assert sorted(used_by) == ["clean_orders", "silver_orders"]

    def test_no_pipelines_use_source(self) -> None:
        from dex_studio.routers.data import _source_used_by

        eng = _make_eng({"p": SimpleNamespace(source="other_source")})

        assert _source_used_by(eng, "unused_source") == []


class TestPipelineGraphView:
    def test_synthesizes_from_yaml_when_unmigrated(self) -> None:
        with TemporaryDirectory() as tmp:
            sdb = StudioDb(Path(tmp) / "studio.db")
            cfg = SimpleNamespace(
                source="raw_orders",
                destination="silver_orders",
                steps=[SimpleNamespace(type="filter", name="", sql="")],
            )
            eng = _make_eng({"clean_orders": cfg})

            view = _pipeline_graph_view(eng, sdb, "clean_orders", cfg)

            assert view["migrated"] is False
            kinds = [n["kind"] for n in view["nodes"]]
            assert kinds == ["source", "transform", "sink"]
            assert len(view["edges"]) == 2
            assert view["edges"][0]["from"] == view["nodes"][0]["id"]
            assert view["edges"][0]["to"] == view["nodes"][1]["id"]

    def test_uses_db_model_when_migrated(self) -> None:
        with TemporaryDirectory() as tmp:
            sdb = StudioDb(Path(tmp) / "studio.db")
            from dex_studio.pipeline_definition import PipelineDefinitionStore

            store = PipelineDefinitionStore(sdb)
            store.import_from_yaml_steps(
                project_id="default",
                pipeline_name="clean_orders",
                source="raw_orders",
                destination="silver_orders",
                schedule="",
                depends_on=[],
                steps=[{"type": "filter", "condition": "x > 0"}],
            )
            cfg = SimpleNamespace(source="raw_orders", destination="silver_orders", steps=[])
            eng = _make_eng({"clean_orders": cfg})

            view = _pipeline_graph_view(eng, sdb, "clean_orders", cfg)

            assert view["migrated"] is True
            kinds = [n["kind"] for n in view["nodes"]]
            assert kinds == ["source", "transform", "sink"]

    def test_no_studio_db_synthesizes_from_yaml(self) -> None:
        cfg = SimpleNamespace(source="raw", destination="silver", steps=[])
        eng = _make_eng({"p": cfg})

        view = _pipeline_graph_view(eng, None, "p", cfg)

        assert view["migrated"] is False
        assert [n["kind"] for n in view["nodes"]] == ["source", "sink"]
        assert len(view["edges"]) == 1


class TestTableQualityChecks:
    def test_filters_checks_by_table(self) -> None:
        from unittest.mock import MagicMock

        from dex_studio.routers.data import _table_quality_checks

        eng = MagicMock()
        eng.quality_history.return_value = {
            "runs": [
                {
                    "timestamp": "2026-07-11T00:00:00Z",
                    "results": {
                        "silver_orders": {
                            "score": 1.0,
                            "completeness": 1.0,
                            "uniqueness": 1.0,
                            "passed": True,
                        },
                        "silver_users": {
                            "score": 0.5,
                            "completeness": 0.5,
                            "uniqueness": 0.5,
                            "passed": False,
                        },
                    },
                },
            ],
        }

        result = _table_quality_checks(eng, "silver_orders")

        assert len(result) == 1
        assert result[0]["table"] == "silver_orders"
        assert result[0]["passed"] is True

    def test_no_runs_returns_empty(self) -> None:
        from unittest.mock import MagicMock

        from dex_studio.routers.data import _table_quality_checks

        eng = MagicMock()
        eng.quality_history.return_value = {"runs": []}

        assert _table_quality_checks(eng, "any_table") == []


class TestPipelineLineageView:
    def test_upstream_from_yaml_when_unmigrated(self) -> None:
        with TemporaryDirectory() as tmp:
            sdb = StudioDb(Path(tmp) / "studio.db")
            cfg_a = SimpleNamespace(depends_on=["raw_orders"])
            cfg_b = SimpleNamespace(depends_on=[])
            eng = _make_eng({"clean_orders": cfg_a, "raw_orders": cfg_b})

            view = _pipeline_lineage_view(eng, sdb, "clean_orders")

            assert view["upstream"] == ["raw_orders"]
            assert view["downstream"] == []

    def test_downstream_finds_dependents(self) -> None:
        with TemporaryDirectory() as tmp:
            sdb = StudioDb(Path(tmp) / "studio.db")
            cfg_a = SimpleNamespace(depends_on=[])
            cfg_b = SimpleNamespace(depends_on=["raw_orders"])
            cfg_c = SimpleNamespace(depends_on=["raw_orders"])
            eng = _make_eng({"raw_orders": cfg_a, "clean_orders": cfg_b, "silver_orders": cfg_c})

            view = _pipeline_lineage_view(eng, sdb, "raw_orders")

            assert view["upstream"] == []
            assert sorted(view["downstream"]) == ["clean_orders", "silver_orders"]

    def test_upstream_prefers_db_model(self) -> None:
        with TemporaryDirectory() as tmp:
            sdb = StudioDb(Path(tmp) / "studio.db")
            from dex_studio.pipeline_definition import PipelineDefinitionStore

            PipelineDefinitionStore(sdb).import_from_yaml_steps(
                project_id="default",
                pipeline_name="clean_orders",
                source="raw_orders",
                destination="silver_orders",
                schedule="",
                depends_on=["db_upstream"],
                steps=[],
            )
            cfg = SimpleNamespace(depends_on=["yaml_upstream"])
            eng = _make_eng({"clean_orders": cfg})

            view = _pipeline_lineage_view(eng, sdb, "clean_orders")

            assert view["upstream"] == ["db_upstream"]

    def test_upstream_trusts_db_empty_over_stale_yaml(self) -> None:
        """A migrated root pipeline with depends_on=[] in the DB must not fall back
        to a stale YAML config that still lists a (now-removed) upstream."""
        with TemporaryDirectory() as tmp:
            sdb = StudioDb(Path(tmp) / "studio.db")
            from dex_studio.pipeline_definition import PipelineDefinitionStore

            PipelineDefinitionStore(sdb).import_from_yaml_steps(
                project_id="default",
                pipeline_name="clean_orders",
                source="raw_orders",
                destination="silver_orders",
                schedule="",
                depends_on=[],
                steps=[],
            )
            cfg = SimpleNamespace(depends_on=["stale_yaml_upstream"])
            eng = _make_eng({"clean_orders": cfg})

            view = _pipeline_lineage_view(eng, sdb, "clean_orders")

            assert view["upstream"] == []


class TestExtractMissingSource:
    def test_extracts_name_from_known_error_format(self) -> None:
        from dex_studio.routers.data import _extract_missing_source

        error = "Source 'silver_orders' not found in data.sources or data.pipelines. "
        assert _extract_missing_source(error) == "silver_orders"

    def test_returns_empty_for_unrelated_error(self) -> None:
        from dex_studio.routers.data import _extract_missing_source

        assert _extract_missing_source("Connection timed out") == ""

    def test_returns_empty_for_empty_string(self) -> None:
        from dex_studio.routers.data import _extract_missing_source

        assert _extract_missing_source("") == ""
