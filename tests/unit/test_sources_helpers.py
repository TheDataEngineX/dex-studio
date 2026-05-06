"""Tests for DexEngine source query helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dex_studio.engine import DexEngine


@pytest.fixture
def engine() -> DexEngine:
    """Create a DexEngine with the movie-dex config."""
    return DexEngine(Path("/home/jay/workspace/DataEngineX/dex-studio/movie-dex/dex.yaml"))


def test_source_row_count_returns_int_or_none(engine: DexEngine) -> None:
    """source_row_count returns an integer or None."""
    sources = list(engine.config.data.sources.keys())
    assert len(sources) >= 1
    result = engine.source_row_count(sources[0])
    assert result is None or isinstance(result, int)


def test_source_schema_returns_list_or_none(engine: DexEngine) -> None:
    """source_schema returns a list of column dicts or None."""
    sources = list(engine.config.data.sources.keys())
    result = engine.source_schema(sources[0])
    if result is not None:
        assert isinstance(result, list)
        if result:
            assert "column_name" in result[0]
            assert "column_type" in result[0]
            assert "nullable" in result[0]


def test_source_sample_returns_list_or_none(engine: DexEngine) -> None:
    """source_sample returns a list of row dicts or None."""
    sources = list(engine.config.data.sources.keys())
    result = engine.source_sample(sources[0], limit=5, offset=0)
    if result is not None:
        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], dict)


def test_source_stats_returns_dict_or_none(engine: DexEngine) -> None:
    """source_stats returns a dict with expected keys or None."""
    sources = list(engine.config.data.sources.keys())
    result = engine.source_stats(sources[0])
    if result is not None:
        assert isinstance(result, dict)
        assert "row_count" in result
        assert "column_count" in result
        assert "size_bytes" in result
        assert "path" in result
        assert "connector_type" in result


def test_source_stats_unknown_returns_none(engine: DexEngine) -> None:
    """source_stats returns None for unknown source name."""
    result = engine.source_stats("nonexistent_source_xyz")
    assert result is None


def test_source_row_count_unknown_returns_none(engine: DexEngine) -> None:
    """source_row_count returns None for unknown source name."""
    result = engine.source_row_count("nonexistent_source_xyz")
    assert result is None


def test_source_schema_unknown_returns_none(engine: DexEngine) -> None:
    """source_schema returns None for unknown source name."""
    result = engine.source_schema("nonexistent_source_xyz")
    assert result is None


def test_source_sample_unknown_returns_none(engine: DexEngine) -> None:
    """source_sample returns None for unknown source name."""
    result = engine.source_sample("nonexistent_source_xyz")
    assert result is None


def test_source_sample_pagination(engine: DexEngine) -> None:
    """source_sample with limit and offset works."""
    sources = list(engine.config.data.sources.keys())
    result = engine.source_sample(sources[0], limit=2, offset=0)
    if result is not None:
        assert len(result) <= 2


def test_get_source_path_returns_tuple_or_none(engine: DexEngine) -> None:
    """_get_source_path returns (src, Path) or None."""
    sources = list(engine.config.data.sources.keys())
    result = engine._get_source_path(sources[0])
    if result is not None:
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[1], Path)


def test_source_read_function_returns_str_or_none(engine: DexEngine) -> None:
    """_source_read_function returns read function name or None."""
    sources = list(engine.config.data.sources.keys())
    result = engine._source_read_function(sources[0])
    assert result is None or isinstance(result, str)
