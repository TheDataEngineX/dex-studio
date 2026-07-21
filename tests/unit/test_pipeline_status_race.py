"""Regression tests — pipeline status race condition (Bug 3 fix).

Before the fix: _build_pipeline_rows() always read status from DB/engine,
so a freshly triggered pipeline showed "failed" (from last DB run) until the
background thread wrote its first record.

After the fix: is_pipeline_running(name) is checked; if True, status = "running"
overrides whatever the DB says.

NOTE: jobs.py was refactored from an in-memory tracking scheme (module-level
``_lock``/``_running``/``_started_at``) to a DB-backed scheme where running/queued
state is read from StudioDb/PgStudioDb via ``db.get_queue_status()``. These tests
were ported accordingly — "add to _running" becomes "mock db.get_queue_status()
to report the pipeline as running", passed explicitly via the ``db=`` parameter
that is_pipeline_running/run_pipeline_bg/etc. already accept.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

# ── helpers ──────────────────────────────────────────────────────────────────


def _mock_engine(pipelines: dict | None = None) -> MagicMock:
    eng = MagicMock()
    eng.config.data.pipelines = pipelines or {}
    # Use a real temporary directory instead of MagicMock to avoid creating
    # directories with MagicMock's string representation
    tmp = TemporaryDirectory()
    eng._dex_dir = Path(tmp.name)
    eng._tmp_dir = tmp  # Keep reference to prevent cleanup during test
    return eng


def _queue_status(entries: list[dict] | None = None) -> dict:
    """Build a get_queue_status()-shaped dict, matching StudioDb.get_queue_status's
    real return shape: {"total": int, "by_status": {status: count}, "entries": [...]}."""
    entries = entries or []
    by_status: dict[str, int] = {}
    for e in entries:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    return {"total": len(entries), "by_status": by_status, "entries": entries}


def _queue_entry(name: str, status: str, **overrides: object) -> dict:
    entry = {
        "pipeline_name": name,
        "status": status,
        "priority": 50,
        "depends_on": [],
        "triggered_by": "manual",
        "started_at": None,
        "finished_at": None,
        "error_msg": "",
        "version": 1,
    }
    entry.update(overrides)
    return entry


# ── is_pipeline_running ──────────────────────────────────────────────────────


class TestIsPipelineRunning:
    def test_returns_false_initially(self) -> None:
        from dex_studio.jobs import is_pipeline_running

        assert is_pipeline_running("nonexistent_pipeline_xyz") is False

    def test_returns_true_when_in_running_set(self) -> None:
        from dex_studio.jobs import is_pipeline_running

        name = "__test_pipeline_status_race__"
        db = MagicMock()
        db.get_queue_status.return_value = _queue_status([_queue_entry(name, "running")])

        assert is_pipeline_running(name, db=db) is True

    def test_returns_false_after_removal(self) -> None:
        from dex_studio.jobs import is_pipeline_running

        name = "__test_pipeline_status_race_remove__"
        db = MagicMock()
        # Simulate the entry no longer being in the queue (finished/removed).
        db.get_queue_status.return_value = _queue_status([])

        assert is_pipeline_running(name, db=db) is False


# ── _build_pipeline_rows status override ────────────────────────────────────


class TestBuildPipelineRowsStatusOverride:
    def _make_pipe_cfg(self) -> MagicMock:
        cfg = MagicMock()
        cfg.destination = "silver.test"
        cfg.source = "raw"
        cfg.schedule = ""
        cfg.depends_on = []
        cfg.steps = []
        cfg.transforms = []
        return cfg

    def _make_last_run(self, success: bool) -> MagicMock:
        run = MagicMock()
        run.success = success
        run.timestamp = "2026-01-01T00:00:00+00:00"
        run.duration_ms = 100.0
        run.rows_input = 10
        run.rows_output = 10
        return run

    def test_failed_last_run_but_running_shows_running(self) -> None:
        """Core regression: pipeline's last run was a failure, but it's currently
        running (per is_pipeline_running) -> status must be 'running', not 'failed'."""
        pipe_name = "test_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=False)

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=None),
            patch("dex_studio.routers.data.is_pipeline_running", return_value=True),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "running", (
            f"Expected 'running' but got '{rows[0]['status']}' — "
            "race condition not fixed: is_pipeline_running check missing"
        )

    def test_never_run_but_running_shows_running(self) -> None:
        """No DB record yet, but pipeline just triggered -> must show 'running'."""
        pipe_name = "fresh_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = None

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=None),
            patch("dex_studio.routers.data.is_pipeline_running", return_value=True),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "running"

    def test_not_running_keeps_db_status(self) -> None:
        """Pipeline not running -> DB status is authoritative."""
        pipe_name = "idle_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=True)

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=None),
            patch("dex_studio.routers.data.is_pipeline_running", return_value=False),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "success"

    def test_failed_not_running_keeps_failed(self) -> None:
        """Failed pipeline not currently running -> stays 'failed'."""
        pipe_name = "failed_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=False)

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=None),
            patch("dex_studio.routers.data.is_pipeline_running", return_value=False),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "failed"


# ── run_pipeline_bg cross-pod claim timing ──────────────────────────────────
#
# The DB-backed queue (tested above via get_queue_status) is what makes the
# race visible cross-pod, not just in-process: any pod reading get_queue_status
# sees "running" as soon as the row is claimed. Before this architecture, the
# equivalent guarantee was "the DB lock must be acquired before the job is
# handed to the executor, and a worker that already holds the claim must not
# re-acquire/re-claim it." In the current API, the "claim" is the atomic
# db.claim_next_queued() row update (status queued -> running via optimistic
# locking), done by _start_next_queued() *before* _EXECUTOR.submit() is ever
# called — and _run(name, claimed) is handed the already-claimed record, so it
# must never call claim_next_queued (or acquire_lock) again for the same run.


class TestRunPipelineBgLockTiming:
    def test_acquires_db_lock_before_submitting_job(self) -> None:
        """run_pipeline_bg must claim the queue row (atomic DB claim) before
        handing the run to the executor — the executor receives the already-
        claimed record, proving claim-then-submit ordering."""
        import dex_studio.jobs as jobs_mod

        name = "__test_lock_timing_free__"
        sdb = MagicMock()
        sdb.get_queue_status.return_value = _queue_status([])
        claimed = _queue_entry(name, "running", id=1, version=1)
        sdb.claim_next_queued.return_value = claimed
        eng = MagicMock()
        eng.config.data.pipelines = {}
        eng.config.scheduler = None  # force _get_scheduler_config's default fallback

        with (
            patch.object(jobs_mod, "_available_mb", return_value=999_999),
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
            patch.object(jobs_mod._EXECUTOR, "submit") as mock_submit,
        ):
            result = jobs_mod.run_pipeline_bg(name)

        sdb.claim_next_queued.assert_called_once_with(jobs_mod._MAX_CONCURRENT)
        mock_submit.assert_called_once_with(jobs_mod._run, name, claimed=claimed)
        assert result == "started"

    def test_returns_running_without_submitting_when_locked_elsewhere(self) -> None:
        """Another pod (or the scheduler) already claimed this pipeline in the
        DB queue — don't double-run."""
        import dex_studio.jobs as jobs_mod

        name = "__test_lock_timing_held__"
        sdb = MagicMock()
        sdb.get_queue_status.return_value = _queue_status([_queue_entry(name, "running")])
        eng = MagicMock()
        eng.config.data.pipelines = {}

        with (
            patch.object(jobs_mod, "_available_mb", return_value=999_999),
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
            patch.object(jobs_mod._EXECUTOR, "submit") as mock_submit,
        ):
            result = jobs_mod.run_pipeline_bg(name)

        sdb.enqueue_pipeline.assert_not_called()
        mock_submit.assert_not_called()
        assert result == "running"

    def test_worker_does_not_reclaim_queue_row_but_does_take_the_run_lock(self) -> None:
        """_run(name, claimed) must not re-claim the queue row it was already
        handed by _start_next_queued's atomic claim (that's a separate,
        already-exclusive DB transition) — but it must still acquire the
        pipeline's advisory run-lock via StudioDb.acquire_lock().

        Previously this path skipped acquire_lock() entirely, on the
        assumption that the queue claim alone was sufficient exclusivity.
        That left every queue-executed run without a pipeline_locks row, so
        scheduler._reconcile_stale_locks() — which treats any 'running'
        pipeline_runs row with no held lock as orphaned — force-reconciled
        (silently killed) every queue-executed run the instant a scheduler
        tick landed while it was still legitimately in progress. Crashed
        queue-executed runs also had no other liveness check, so they'd get
        stuck at 'running' forever with no automatic recovery at all.
        """
        import dex_studio.jobs as jobs_mod

        name = "__test_no_double_acquire__"
        sdb = MagicMock()
        sdb.acquire_lock.return_value = True
        sdb.start_run.return_value = 1
        sdb.get_queue_status.return_value = _queue_status([])
        eng = MagicMock()
        eng.run_pipeline.return_value = None
        claimed = _queue_entry(name, "running", id=1, version=1)

        with (
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
            patch.object(jobs_mod, "_run_pipeline_with_timeout", return_value=None),
            patch.object(jobs_mod, "_post_success_checks"),
            patch.object(jobs_mod, "_trigger_dependents"),
            patch.object(jobs_mod, "_push_pipeline_toast"),
            patch.object(jobs_mod, "_start_next_queued"),
        ):
            jobs_mod._run(name, claimed)

        sdb.acquire_lock.assert_called_once_with(name)
        sdb.release_lock.assert_called_once_with(name)
        sdb.claim_next_queued.assert_not_called()
        sdb.start_run.assert_called_once_with(name, triggered_by="manual")

    def test_worker_requeues_when_lock_held_by_another_path(self) -> None:
        """If scheduler.py's _run_one_pipeline (retries/dependents) already
        holds this pipeline's advisory lock, _run() must not execute it —
        and must reset the queue row back to 'queued' (not leave it stuck at
        'running' forever, and not mark it failed/cancelled, which would
        burn a retry attempt or misreport what happened)."""
        import dex_studio.jobs as jobs_mod

        name = "__test_lock_held_elsewhere__"
        sdb = MagicMock()
        sdb.acquire_lock.return_value = False
        sdb.get_queue_status.return_value = _queue_status([])
        eng = MagicMock()
        claimed = _queue_entry(name, "running", id=7, version=2)

        with (
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
            patch.object(jobs_mod, "_run_pipeline_with_timeout") as mock_execute,
            patch.object(jobs_mod, "_push_pipeline_toast"),
            patch.object(jobs_mod, "_start_next_queued"),
        ):
            jobs_mod._run(name, claimed)

        sdb.acquire_lock.assert_called_once_with(name)
        sdb.release_lock.assert_not_called()
        sdb.start_run.assert_not_called()
        mock_execute.assert_not_called()
        sdb.mark_queue_status.assert_called_once_with(
            7,
            "queued",
            "pipeline locked by another run",
            None,
            2,
        )
