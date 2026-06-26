"""Regression tests — pipeline status race condition (Bug 3 fix).

Before the fix: _build_pipeline_rows() always read status from DB/engine,
so a freshly triggered pipeline showed "failed" (from last DB run) until the
background thread wrote its first record.

After the fix: is_pipeline_running(name) is checked; if True, status = "running"
overrides whatever the DB says.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── helpers ──────────────────────────────────────────────────────────────────


def _mock_engine(pipelines: dict | None = None) -> MagicMock:
    eng = MagicMock()
    eng.config.data.pipelines = pipelines or {}
    eng._dex_dir = MagicMock()
    eng._dex_dir.__truediv__ = lambda self, other: MagicMock(exists=lambda: False)
    return eng


# ── is_pipeline_running ───────────────────────────────────────────────────────


class TestIsPipelineRunning:
    def test_returns_false_initially(self) -> None:
        from dex_studio.jobs import is_pipeline_running

        assert is_pipeline_running("nonexistent_pipeline_xyz") is False

    def test_returns_true_when_in_running_set(self) -> None:
        from dex_studio.jobs import _lock, _running, is_pipeline_running

        name = "__test_pipeline_status_race__"
        with _lock:
            _running.add(name)
        try:
            assert is_pipeline_running(name) is True
        finally:
            with _lock:
                _running.discard(name)

    def test_returns_false_after_removal(self) -> None:
        from dex_studio.jobs import _lock, _running, is_pipeline_running

        name = "__test_pipeline_status_race_remove__"
        with _lock:
            _running.add(name)
        with _lock:
            _running.discard(name)
        assert is_pipeline_running(name) is False


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
        in _running → status must be 'running', not 'failed'."""
        from dex_studio.jobs import _lock, _running

        pipe_name = "test_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = self._make_last_run(success=False)

        with _lock:
            _running.add(pipe_name)
        try:
            with patch("dex_studio.routers.data.get_studio_db", return_value=None):
                from dex_studio.routers.data import _build_pipeline_rows

                rows = _build_pipeline_rows(eng)
        finally:
            with _lock:
                _running.discard(pipe_name)

        assert len(rows) == 1
        assert rows[0]["status"] == "running", (
            f"Expected 'running' but got '{rows[0]['status']}' — "
            "race condition not fixed: is_pipeline_running check missing"
        )

    def test_never_run_but_running_shows_running(self) -> None:
        """No DB record yet, but pipeline just triggered → must show 'running'."""
        from dex_studio.jobs import _lock, _running

        pipe_name = "fresh_pipe"
        eng = _mock_engine({pipe_name: self._make_pipe_cfg()})
        eng.pipeline_last_run.return_value = None

        with _lock:
            _running.add(pipe_name)
        try:
            with patch("dex_studio.routers.data.get_studio_db", return_value=None):
                from dex_studio.routers.data import _build_pipeline_rows

                rows = _build_pipeline_rows(eng)
        finally:
            with _lock:
                _running.discard(pipe_name)

        assert len(rows) == 1
        assert rows[0]["status"] == "running"

    def test_not_running_keeps_db_status(self) -> None:
        """Pipeline not in _running → DB status is authoritative."""
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
        """Failed pipeline not currently running → stays 'failed'."""
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
