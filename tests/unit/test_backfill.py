"""Regression tests for BackfillEngine's crash-checkpoint/resume logic."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from dex_studio.backfill import BackfillEngine
from dex_studio.studio_db import StudioDb


@pytest.fixture
def db():
    with TemporaryDirectory() as tmp:
        d = StudioDb(Path(tmp) / "studio.db")
        yield d


def _make_engine() -> MagicMock:
    eng = MagicMock()
    eng.config.data.pipelines = {}
    return eng


class TestBackfillCheckpoint:
    def test_trigger_all_persists_batch_progress(self, db: StudioDb) -> None:
        bf = BackfillEngine(_make_engine(), db)
        with patch.object(
            BackfillEngine,
            "trigger",
            side_effect=lambda name, **_: {"pipeline": name, "error": ""},
        ):
            results = bf.trigger_all(["a", "b"], run_now=False)

        batch_id = results[0]["batch_id"]
        rows = {r["pipeline"]: r for r in db.get_backfill_batch(batch_id)}
        assert rows["a"]["status"] == "success"
        assert rows["b"]["status"] == "success"
        assert db.list_incomplete_backfill_batches() == []

    def test_trigger_all_records_failures(self, db: StudioDb) -> None:
        bf = BackfillEngine(_make_engine(), db)

        def fake_trigger(name: str, **_: object) -> dict[str, object]:
            return {"pipeline": name, "error": "boom" if name == "b" else ""}

        with patch.object(BackfillEngine, "trigger", side_effect=fake_trigger):
            results = bf.trigger_all(["a", "b"], run_now=False)

        batch_id = results[0]["batch_id"]
        rows = {r["pipeline"]: r for r in db.get_backfill_batch(batch_id)}
        assert rows["a"]["status"] == "success"
        assert rows["b"]["status"] == "failed"
        assert db.list_incomplete_backfill_batches() == []  # no 'pending' left, just failed

    def test_resume_batch_only_retries_non_success(self, db: StudioDb) -> None:
        """Crash-mid-batch scenario: 'a' finished, 'b' and 'c' never ran (still pending)."""
        bf = BackfillEngine(_make_engine(), db)
        db.create_backfill_batch("crashed-batch", ["a", "b", "c"])
        db.mark_backfill_pipeline("crashed-batch", "a", "success")

        attempted: list[str] = []
        with patch.object(
            BackfillEngine,
            "trigger",
            side_effect=lambda name, **_: attempted.append(name) or {"pipeline": name, "error": ""},
        ):
            bf.resume_batch("crashed-batch", run_now=False)

        assert sorted(attempted) == ["b", "c"]  # 'a' skipped, already succeeded

    def test_resume_batch_noop_when_fully_succeeded(self, db: StudioDb) -> None:
        bf = BackfillEngine(_make_engine(), db)
        db.create_backfill_batch("done-batch", ["a"])
        db.mark_backfill_pipeline("done-batch", "a", "success")

        with patch.object(BackfillEngine, "trigger") as mock_trigger:
            results = bf.resume_batch("done-batch", run_now=False)

        mock_trigger.assert_not_called()
        assert results == []

    def test_list_incomplete_batches_surfaces_crashed_batch(self, db: StudioDb) -> None:
        bf = BackfillEngine(_make_engine(), db)
        db.create_backfill_batch("crashed-batch", ["a", "b"])
        db.mark_backfill_pipeline("crashed-batch", "a", "success")
        # 'b' never got marked — simulates the process dying before it ran.

        assert bf.list_incomplete_batches() == ["crashed-batch"]
