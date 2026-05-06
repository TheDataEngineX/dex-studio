"""Tests for DexEngine pipeline query helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dex_studio.engine import DexEngine


@pytest.fixture
def engine() -> DexEngine:
    """Create a DexEngine with the movie-dex config."""
    return DexEngine(Path("/home/jay/workspace/DataEngineX/dex-studio/movie-dex/dex.yaml"))


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
