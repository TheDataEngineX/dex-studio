"""Tests for the MovieDEX idempotent RabbitMQ enrichment handler."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from dataenginex.lakehouse.storage import DeltaStorage
from dataenginex.orm import JobState, get_session

PLUGIN = (
    Path(__file__).parents[2] / "examples" / "movie-dex" / "plugins" / "movie_enrichment_handler.py"
)


def _load_plugin() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_movie_enrichment_handler", PLUGIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Connector:
    def __init__(self, result: dict[str, Any] | None) -> None:
        self.result = result
        self.calls = 0

    def fetch_one(self, tmdb_id: int) -> dict[str, Any] | None:
        self.calls += 1
        return dict(self.result) if self.result is not None else None


def test_handler_is_idempotent_and_persists_delta_event(tmp_path: Path) -> None:
    module = _load_plugin()
    connector = _Connector({"id": 101, "title": "Example"})
    output = tmp_path / "lakehouse" / "events"
    handler = module.MovieEnrichmentHandler(
        connector,
        output_path=output,
        db_url=f"sqlite:///{tmp_path / 'jobs.db'}",
    )
    message = {"job_id": "tmdb-movie-101", "movie_id": 101}

    assert handler(message) is True
    assert handler(message) is True
    assert connector.calls == 1

    rows = DeltaStorage(base_path=str(output.parent)).read(output.name)
    assert len(rows) == 1
    assert rows[0]["id"] == 101
    assert rows[0]["_dex_job_id"] == "tmdb-movie-101"
    with get_session(handler._engine) as session:
        state = session.get(JobState, "tmdb-movie-101")
        assert state is not None
        assert state.status == "done"
    handler._engine.dispose()


def test_handler_records_failed_fetch(tmp_path: Path) -> None:
    module = _load_plugin()
    handler = module.MovieEnrichmentHandler(
        _Connector(None),
        output_path=tmp_path / "lakehouse" / "events",
        db_url=f"sqlite:///{tmp_path / 'jobs.db'}",
    )

    assert handler({"movie_id": 404}) is False
    with get_session(handler._engine) as session:
        state = session.get(JobState, "tmdb-movie-404")
        assert state is not None
        assert state.status == "failed"
        assert state.error_message == "TMDB fetch returned no record"
    handler._engine.dispose()
