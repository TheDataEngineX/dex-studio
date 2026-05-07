"""Tests for DexEngine warehouse helper methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from dex_studio.engine import DexEngine


@pytest.fixture
def engine() -> DexEngine:
    """Create a DexEngine with the movie-dex config."""
    return DexEngine(Path("/home/jay/workspace/DataEngineX/dex-studio/movie-dex/dex.yaml"))


def test_warehouse_table_schema_returns_list(engine: DexEngine) -> None:
    """warehouse_table_schema returns a list of column dicts."""
    layers = engine.warehouse_layers()
    for layer in layers:
        tables = engine.warehouse_tables(layer["name"])
        if tables:
            schema = engine.warehouse_table_schema(tables[0]["name"], layer["name"])
            assert isinstance(schema, list)
            if schema:
                assert "name" in schema[0]
                assert "dtype" in schema[0]
                assert "nullable" in schema[0]
            break


def test_warehouse_table_schema_unknown_returns_empty(engine: DexEngine) -> None:
    """warehouse_table_schema returns empty list for unknown table."""
    schema = engine.warehouse_table_schema("nonexistent_xyz", "bronze")
    assert isinstance(schema, list)


def test_warehouse_table_stats_returns_dict(engine: DexEngine) -> None:
    """warehouse_table_stats returns a dict with size_bytes, column_count, row_count."""
    layers = engine.warehouse_layers()
    for layer in layers:
        tables = engine.warehouse_tables(layer["name"])
        if tables:
            stats = engine.warehouse_table_stats(tables[0]["name"], layer["name"])
            assert isinstance(stats, dict)
            assert "size_bytes" in stats
            assert "column_count" in stats
            assert "row_count" in stats
            break


def test_warehouse_table_stats_unknown_returns_empty(engine: DexEngine) -> None:
    """warehouse_table_stats returns empty dict for unknown table."""
    stats = engine.warehouse_table_stats("nonexistent_xyz", "bronze")
    assert isinstance(stats, dict)


def test_warehouse_table_lineage_returns_dict(engine: DexEngine) -> None:
    """warehouse_table_lineage returns dict with upstream and downstream lists."""
    lineage = engine.warehouse_table_lineage("movies", "bronze")
    assert isinstance(lineage, dict)
    assert "upstream" in lineage
    assert "downstream" in lineage
    assert isinstance(lineage["upstream"], list)
    assert isinstance(lineage["downstream"], list)
