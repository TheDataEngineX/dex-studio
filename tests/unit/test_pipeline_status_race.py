"""Regression tests — pipeline status race condition (Bug 3 fix).

Before the fix: _build_pipeline_rows() always read status from DB/engine,
so a freshly triggered pipeline showed "failed" (from last DB run) until the
background thread wrote its first record.

After the fix: is_pipeline_running(name) is checked; if True, status = "running"
overrides whatever the DB says.

The queue-based refactor replaced the in-memory _running set with a DB-backed
pipeline_queue table. Tests now mock is_pipeline_running / get_queue_status.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

# ── helpers ──────────────────────────────────────────────────────────────────


def _mock_engine(pipelines: dict | None = None) -> MagicMock:
    eng = MagicMock()
    eng.config.data.pipelines = pipelines or {}
    tmp = TemporaryDirectory()
    eng._dex_dir = Path(tmp.name)
    eng._tmp_dir = tmp  # Keep reference to prevent cleanup during test
    return eng


# ── is_pipeline_running ───────────────────────────────────────────────────────


class TestIsPipelineRunning:
    def test_returns_false_initially(self) -> None:
        from dex_studio.jobs import is_pipeline_running

        with patch("dex_studio._engine.get_engine", return_value=None):
            assert is_pipeline_running("nonexistent_pipeline_xyz") is False

    def test_returns_true_when_in_running_set(self) -> None:
        """is_pipeline_running returns True when DB queue shows the pipeline as running."""
        from dex_studio.jobs import is_pipeline_running

        name = "__test_pipeline_status_race__"
        mock_db = MagicMock()
        mock_db.get_queue_status.return_value = {
            "entries": [{"pipeline_name": name, "status": "running"}],
            "total": 1,
            "by_status": {"running": 1},
        }
        assert is_pipeline_running(name, db=mock_db) is True

    def test_returns_false_after_removal(self) -> None:
        """is_pipeline_running returns False when pipeline is not in queue."""
        from dex_studio.jobs import is_pipeline_running

        name = "__test_pipeline_status_race_remove__"
        mock_db = MagicMock()
        mock_db.get_queue_status.return_value = {
            "entries": [],
            "total": 0,
            "by_status": {},
        }
        assert is_pipeline_running(name, db=mock_db) is False


# ── _build_pipeline_rows status override ─────────────────────────────────────


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
        """Core regression: pipeline last run was failure, but it's currently
        running in DB queue → status must be 'running', not 'failed'."""
        pipe_name = "test_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=False)

        running_entry = {"pipeline": pipe_name, "status": "running", "finished_at": None}
        mock_db = MagicMock()
        mock_db.get_runs.side_effect = lambda _name, limit=1: [running_entry] if limit > 1 else []

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=mock_db),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "running", (
            f"Expected 'running' but got '{rows[0]['status']}' — "
            "race condition not fixed: is_pipeline_running check missing"
        )

    def test_never_run_but_running_shows_running(self) -> None:
        """No DB record yet, but pipeline just triggered → must show 'running'."""
        pipe_name = "fresh_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = None

        running_entry = {"pipeline": pipe_name, "status": "running", "finished_at": None}
        mock_db = MagicMock()
        mock_db.get_runs.side_effect = lambda _name, limit=1: [running_entry] if limit > 1 else []

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=mock_db),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "running"

    def test_not_running_keeps_db_status(self) -> None:
        """Pipeline not running in queue → DB status is authoritative."""
        pipe_name = "idle_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=True)

        mock_db = MagicMock()
        mock_db.get_runs.side_effect = lambda _name, limit=1: []

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=mock_db),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "success"

    def test_failed_not_running_keeps_failed(self) -> None:
        """Failed pipeline not currently running → stays 'failed'."""
        pipe_name = "failed_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=False)

        mock_db = MagicMock()
        mock_db.get_runs.side_effect = lambda _name, limit=1: []

        with (
            patch("dex_studio.routers.data.get_studio_db", return_value=mock_db),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.routers.data import _build_pipeline_rows

            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "failed"


# ── run_pipeline_bg queue system ─────────────────────────────────────────────
#
# The queue-based refactor uses DB-backed pipeline_queue table.
# Tests verify the queue flow: enqueue → start → complete.


class TestRunPipelineBgQueueSystem:
    def test_enqueue_and_start(self) -> None:
        """run_pipeline_bg enqueues and starts when queue has capacity."""
        import dex_studio.jobs as jobs_mod

        name = "__test_queue_system__"
        sdb = MagicMock()
        sdb.get_queue_status.return_value = {
            "entries": [],
            "total": 0,
            "by_status": {},
        }
        eng = MagicMock()

        with (
            patch.object(jobs_mod, "_available_mb", return_value=999_999),
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
            patch.object(jobs_mod, "_build_dependency_graph", return_value={name: []}),
            patch.object(jobs_mod, "_start_next_queued"),
        ):
            result = jobs_mod.run_pipeline_bg(name)

        sdb.enqueue_pipeline.assert_called_once()
        assert result == "started"

    def test_returns_running_when_already_queued(self) -> None:
        """run_pipeline_bg returns 'running' if pipeline already in queue."""
        import dex_studio.jobs as jobs_mod

        name = "__test_already_queued__"
        sdb = MagicMock()
        sdb.get_queue_status.return_value = {
            "entries": [{"pipeline_name": name, "status": "running"}],
            "total": 1,
            "by_status": {"running": 1},
        }
        eng = MagicMock()

        with (
            patch.object(jobs_mod, "_available_mb", return_value=999_999),
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
        ):
            result = jobs_mod.run_pipeline_bg(name)

        assert result == "running"

    def test_returns_busy_when_queue_full(self) -> None:
        """run_pipeline_bg returns 'busy' when queue is at capacity."""
        import dex_studio.jobs as jobs_mod

        name = "__test_queue_full__"
        sdb = MagicMock()
        sdb.get_queue_status.return_value = {
            "entries": [{"pipeline_name": f"p{i}", "status": "queued"} for i in range(100)],
            "total": 100,
            "by_status": {"queued": 100},
        }
        eng = MagicMock()

        with (
            patch.object(jobs_mod, "_available_mb", return_value=999_999),
            patch("dex_studio._engine.get_engine", return_value=eng),
            patch("dex_studio.studio_db.get_studio_db", return_value=sdb),
        ):
            result = jobs_mod.run_pipeline_bg(name)

        assert result == "busy"

    def test_returns_low_memory_when_insufficient(self) -> None:
        """run_pipeline_bg returns 'low_memory' when memory is low."""
        import dex_studio.jobs as jobs_mod

        name = "__test_low_memory__"

        with patch.object(jobs_mod, "_available_mb", return_value=100):
            result = jobs_mod.run_pipeline_bg(name)

        assert result == "low_memory"
