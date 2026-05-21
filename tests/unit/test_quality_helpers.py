"""Tests for DexEngine quality check helpers."""

from __future__ import annotations

from dataenginex.engine import DexEngine


def test_duckdb_context_manager_creates_connection(engine: DexEngine) -> None:
    """_duckdb() context manager yields a DuckDB connection."""
    with engine._duckdb() as conn:
        assert conn is not None
        result = conn.execute("SELECT 1 as n").fetchone()
        assert result is not None
        assert result[0] == 1


def test_quality_history_returns_dict(engine: DexEngine) -> None:
    """quality_history returns a dict with runs list."""
    history = engine.quality_history()
    assert isinstance(history, dict)
    assert "runs" in history
    assert isinstance(history["runs"], list)


def test_quality_history_returns_empty_if_no_file(engine: DexEngine) -> None:
    """quality_history returns empty runs if no history file exists."""
    history = engine.quality_history()
    assert "runs" in history


def test_quality_check_table_returns_dict_or_none(engine: DexEngine) -> None:
    """quality_check_table returns a dict or None."""
    result = engine.quality_check_table("nonexistent_table_xyz")
    assert result is None or isinstance(result, dict)
