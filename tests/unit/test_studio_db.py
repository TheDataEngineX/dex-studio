from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dex_studio.studio_db import StudioDb


@pytest.fixture
def db(tmp_path: Path) -> StudioDb:
    return StudioDb(tmp_path / "studio.db")


def test_last_run_none_initially(db: StudioDb):
    assert db.get_last_run("my_pipeline") is None


def test_last_run_roundtrip(db: StudioDb):
    ts = datetime(2026, 6, 19, 3, 0, 0, tzinfo=UTC)
    db.set_last_run("my_pipeline", ts)
    result = db.get_last_run("my_pipeline")
    assert result is not None
    assert result.replace(tzinfo=UTC) == ts


def test_set_last_run_overwrites(db: StudioDb):
    t1 = datetime(2026, 6, 18, 3, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 19, 3, 0, tzinfo=UTC)
    db.set_last_run("p", t1)
    db.set_last_run("p", t2)
    assert db.get_last_run("p").replace(tzinfo=UTC) == t2  # type: ignore[union-attr]


def test_acquire_lock_succeeds_first_time(db: StudioDb):
    assert db.acquire_lock("p") is True


def test_acquire_lock_fails_if_already_held(db: StudioDb):
    db.acquire_lock("p")
    assert db.acquire_lock("p") is False


def test_release_lock_allows_reacquire(db: StudioDb):
    db.acquire_lock("p")
    db.release_lock("p")
    assert db.acquire_lock("p") is True


def test_release_nonexistent_lock_is_noop(db: StudioDb):
    db.release_lock("nonexistent")  # must not raise


def test_clear_stale_locks(db: StudioDb):
    db.acquire_lock("stale")
    cleared = db.clear_stale_locks(timeout_s=0)  # everything older than 0s is stale
    assert cleared >= 1
    assert db.acquire_lock("stale") is True  # lock is gone


def test_dead_letter_empty_initially(db: StudioDb):
    assert db.get_dead_letter() == []


def test_dead_letter_record_and_retrieve(db: StudioDb):
    db.record_dead_letter("p", "timeout", 3)
    rows = db.get_dead_letter()
    assert len(rows) == 1
    assert rows[0]["pipeline"] == "p"
    assert rows[0]["error"] == "timeout"
    assert rows[0]["attempts"] == 3


def test_dead_letter_clear(db: StudioDb):
    db.record_dead_letter("p", "err", 2)
    db.clear_dead_letter("p")
    assert db.get_dead_letter() == []


def test_paused_false_by_default(db: StudioDb):
    assert db.is_paused() is False


def test_pause_roundtrip(db: StudioDb):
    db.set_paused(True)
    assert db.is_paused() is True
    db.set_paused(False)
    assert db.is_paused() is False
