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


def test_backfill_batch_starts_all_pending(db: StudioDb):
    db.create_backfill_batch("b1", ["a", "b", "c"])
    rows = db.get_backfill_batch("b1")
    assert {r["pipeline"] for r in rows} == {"a", "b", "c"}
    assert all(r["status"] == "pending" for r in rows)
    assert db.list_incomplete_backfill_batches() == ["b1"]


def test_backfill_batch_mark_done_updates_status(db: StudioDb):
    db.create_backfill_batch("b1", ["a", "b"])
    db.mark_backfill_pipeline("b1", "a", "success")
    db.mark_backfill_pipeline("b1", "b", "failed", "boom")
    rows = {r["pipeline"]: r for r in db.get_backfill_batch("b1")}
    assert rows["a"]["status"] == "success"
    assert rows["a"]["finished_at"]
    assert rows["b"]["status"] == "failed"
    assert rows["b"]["error"] == "boom"


def test_backfill_batch_complete_not_listed_incomplete(db: StudioDb):
    db.create_backfill_batch("b1", ["a"])
    db.mark_backfill_pipeline("b1", "a", "success")
    assert db.list_incomplete_backfill_batches() == []


def test_backfill_batch_reenqueue_is_noop(db: StudioDb):
    """Resuming re-inserts the same batch_id/pipeline pairs — must not clobber progress."""
    db.create_backfill_batch("b1", ["a", "b"])
    db.mark_backfill_pipeline("b1", "a", "success")
    db.create_backfill_batch("b1", ["a", "b"])  # simulates a retried trigger_all call
    rows = {r["pipeline"]: r for r in db.get_backfill_batch("b1")}
    assert rows["a"]["status"] == "success"  # not reset back to pending
    assert rows["b"]["status"] == "pending"


def test_pipeline_def_tables_exist(db: StudioDb):
    conn = db._conn()
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"pipeline_defs", "pipeline_nodes", "pipeline_edges"} <= tables


def test_create_and_get_pipeline_def(db: StudioDb):
    pid = db.create_pipeline_def(
        "proj1", "clean_orders", schedule="0 * * * *", depends_on=["raw_orders"]
    )
    row = db.get_pipeline_def("proj1", "clean_orders")
    assert row is not None
    assert row["id"] == pid
    assert row["name"] == "clean_orders"
    assert row["schedule"] == "0 * * * *"
    assert row["depends_on"] == ["raw_orders"]


def test_get_pipeline_def_missing_returns_none(db: StudioDb):
    assert db.get_pipeline_def("proj1", "nope") is None


def test_node_and_edge_roundtrip(db: StudioDb):
    pid = db.create_pipeline_def("proj1", "clean_orders")
    db.upsert_node(pid, "n1", "source", "", {"table": "raw_orders"})
    db.upsert_node(pid, "n2", "transform", "filter", {"condition": "amount > 0"})
    db.upsert_edge(pid, "e1", "n1", "n2")

    nodes = {n["id"]: n for n in db.list_nodes(pid)}
    assert nodes["n1"]["kind"] == "source"
    assert nodes["n2"]["transform_type"] == "filter"
    assert nodes["n2"]["config"] == {"condition": "amount > 0"}

    edges = db.list_edges(pid)
    assert len(edges) == 1
    assert edges[0]["from_node_id"] == "n1"
    assert edges[0]["to_node_id"] == "n2"


def test_delete_node_cascades_to_edges(db: StudioDb):
    pid = db.create_pipeline_def("proj1", "p")
    db.upsert_node(pid, "n1", "source", "", {})
    db.upsert_node(pid, "n2", "sink", "", {})
    db.upsert_edge(pid, "e1", "n1", "n2")

    db.delete_node("n1")

    assert db.list_nodes(pid) == [n for n in db.list_nodes(pid) if n["id"] != "n1"]
    assert db.list_edges(pid) == []


def test_upsert_node_replaces_existing(db: StudioDb):
    pid = db.create_pipeline_def("proj1", "p")
    db.upsert_node(pid, "n1", "transform", "filter", {"condition": "a > 0"})
    db.upsert_node(pid, "n1", "transform", "filter", {"condition": "a > 1"})

    nodes = db.list_nodes(pid)
    assert len(nodes) == 1
    assert nodes[0]["config"] == {"condition": "a > 1"}
