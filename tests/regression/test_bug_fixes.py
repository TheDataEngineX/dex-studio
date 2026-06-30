"""Regression tests for the three confirmed bug fixes.

Each test class is labelled with the original bug so a future bisect can
pinpoint exactly which fix a failure is tracking.

Bug 1 — Pipeline status race condition
    _build_pipeline_rows() must show "running" for in-flight pipelines even
    when the most-recent DB record reports "failed" or is absent.

Bug 2 — Dead letter retry not re-queuing
    scheduler_clear_dead_letter() must call run_pipeline_bg() so the pipeline
    is immediately re-queued after its dead-letter state is cleared.

Bug 3 — /secops/privacy and /secops/policies returned 404
    Both routes now exist and their templates are present; HTTP 200 expected.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import dex_studio.jobs as jobs_mod
from dex_studio.auth import _hash_password
from dex_studio.routers.data import _build_pipeline_rows
from dex_studio.scheduler import scheduler_clear_dead_letter
from dex_studio.studio_db import StudioDb

# ── Shared helpers ─────────────────────────────────────────────────────────────

_API_KEY = "regression-test-key"  # gitleaks:allow
_SESSION_SECRET = "r" * 32


def _patch_db(monkeypatch: pytest.MonkeyPatch, *, return_hash: str | None = None) -> None:
    monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=return_hash))
    monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
    monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())


class _PipeCfg:
    def __init__(
        self,
        destination: str = "silver.test",
        schedule: str = "",
        depends_on: list[str] | None = None,
    ) -> None:
        self.destination = destination
        self.schedule = schedule
        self.depends_on = depends_on or []
        self.source = "src"
        self.transforms = []
        self.steps = []


def _make_engine_mock() -> MagicMock:
    """Full engine mock — satisfies all route-level attribute accesses."""
    eng = MagicMock()
    eng.config.project.name = "TestProject"
    eng.config_path = "/tmp/test.yaml"
    eng.config.data.sources = {}
    eng.config.data.pipelines = {}
    eng.config.ai = MagicMock()
    eng.config.ai.agents = {}
    eng.agents = {}
    eng.pipeline_stats.return_value = {"total": 0, "scheduled": 0, "failed": 0, "running": 0}
    eng.health.return_value = {"status": "ok", "components": {}}
    eng.model_registry.list_models.return_value = []
    eng.warehouse_layers.return_value = []
    eng.warehouse_tables.return_value = []
    eng.store.get_pipeline_runs.return_value = []
    eng.store.list_model_artifacts.return_value = []
    eng.store.list_experiments.return_value = []
    eng.store.lineage_summary.return_value = {"total_events": 0, "by_layer": {}, "by_operation": {}}
    eng.store.get_memory.return_value = []
    eng.ai_memory = None
    eng.ai_long_memory = None
    eng.ai_episodic = None
    eng.ai_audit = None
    eng.ai_metrics = None
    return eng


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Authenticated TestClient with a mocked engine — no real dex.yaml needed."""
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    _patch_db(monkeypatch, return_hash=_hash_password(_API_KEY))
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303), f"login failed: {resp.status_code}"
        return client


@pytest.fixture(autouse=True)
def _clean_running_set() -> Any:
    """Ensure _running is empty before/after every regression test."""
    with jobs_mod._lock:
        jobs_mod._running.clear()
    yield
    with jobs_mod._lock:
        jobs_mod._running.clear()


# ── Bug 1 regression ──────────────────────────────────────────────────────────


class TestBug1PipelineStatusRace:
    """Regression: in-flight pipeline must show 'running' in the pipeline table rows."""

    def test_pipeline_added_to_running_set_shows_running_in_rows(self) -> None:
        """Core regression: simulate a background thread adding to _running, then
        call _build_pipeline_rows and verify 'running' appears in the output."""
        failed_run = MagicMock()
        failed_run.success = False
        failed_run.timestamp = None
        failed_run.duration_ms = None
        failed_run.rows_input = 0
        failed_run.rows_output = 0

        eng = MagicMock()
        eng.config.data.pipelines = {"ingest": _PipeCfg()}
        eng.pipeline_last_run.return_value = failed_run
        eng._dex_dir = MagicMock()
        eng._dex_dir.__truediv__ = lambda s, o: MagicMock(exists=lambda: False)

        # Simulate the background thread marking the pipeline as running
        with jobs_mod._lock:
            jobs_mod._running.add("ingest")

        with patch("dex_studio.routers.data.get_studio_db", return_value=None):
            rows = _build_pipeline_rows(eng)

        assert len(rows) == 1
        assert rows[0]["status"] == "running", (
            "Regression: pipeline in _running set must report status='running' "
            "even if last DB record was 'failed'"
        )

    def test_race_window_simulation(self) -> None:
        """Simulate the actual race: background thread starts pipeline, main thread
        reads status.  Without the fix the test would see 'failed'; with the fix 'running'."""
        failed_run = MagicMock()
        failed_run.success = False
        failed_run.timestamp = None
        failed_run.duration_ms = None
        failed_run.rows_input = 0
        failed_run.rows_output = 0

        eng = MagicMock()
        eng.config.data.pipelines = {"ingest": _PipeCfg()}
        eng.pipeline_last_run.return_value = failed_run
        eng._dex_dir = MagicMock()
        eng._dex_dir.__truediv__ = lambda s, o: MagicMock(exists=lambda: False)

        rows_captured: list[list[dict]] = []
        ready = threading.Event()

        def _bg_run() -> None:
            """Simulate jobs.run_pipeline_bg adding name to _running, then sleeping."""
            with jobs_mod._lock:
                jobs_mod._running.add("ingest")
            ready.set()
            # Hold for a moment (pipeline "running")
            time.sleep(0.05)
            with jobs_mod._lock:
                jobs_mod._running.discard("ingest")

        t = threading.Thread(target=_bg_run, daemon=True)
        t.start()
        ready.wait(timeout=1.0)

        # Read rows while pipeline is mid-flight
        with patch("dex_studio.routers.data.get_studio_db", return_value=None):
            rows_captured.append(_build_pipeline_rows(eng))

        t.join()

        assert rows_captured[0][0]["status"] == "running", (
            "During mid-flight window, status must be 'running'"
        )

    def test_status_reverts_to_failed_after_pipeline_finishes(self) -> None:
        """After the pipeline finishes and is removed from _running, status goes
        back to whatever the DB says (failed in this case)."""
        failed_run = MagicMock()
        failed_run.success = False
        failed_run.timestamp = None
        failed_run.duration_ms = None
        failed_run.rows_input = 0
        failed_run.rows_output = 0

        eng = MagicMock()
        eng.config.data.pipelines = {"ingest": _PipeCfg()}
        eng.pipeline_last_run.return_value = failed_run
        eng._dex_dir = MagicMock()
        eng._dex_dir.__truediv__ = lambda s, o: MagicMock(exists=lambda: False)

        # Pipeline is NOT running — _running set is empty (via autouse fixture)
        with patch("dex_studio.routers.data.get_studio_db", return_value=None):
            rows = _build_pipeline_rows(eng)

        assert rows[0]["status"] == "failed"


# ── Bug 2 regression ──────────────────────────────────────────────────────────


class TestBug2DeadLetterRetry:
    """Regression: clearing dead letter must immediately re-queue the pipeline."""

    def test_run_pipeline_bg_called_after_dead_letter_clear(self) -> None:
        """After scheduler_clear_dead_letter, run_pipeline_bg must have been called."""
        eng = MagicMock()
        eng.config_path = None

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=None),
            patch("dex_studio.jobs.run_pipeline_bg") as mock_run,
        ):
            mock_run.return_value = "started"
            scheduler_clear_dead_letter(eng, "stuck_pipeline")

        mock_run.assert_called_once_with("stuck_pipeline")

    def test_pipeline_added_to_running_set_after_real_run_pipeline_bg(self) -> None:
        """Integration: after clear, run_pipeline_bg adds name to _running set.

        We patch _available_mb to return plenty of memory so run_pipeline_bg
        does not short-circuit, and we patch _EXECUTOR.submit to avoid actually
        spawning a thread. get_store is imported lazily inside _run(), not at
        module level, so we patch the dex_studio.store module directly.
        """
        eng = MagicMock()
        eng.config_path = None

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=None),
            patch("dex_studio.jobs._available_mb", return_value=99_999),
            patch("dex_studio.jobs._EXECUTOR.submit"),
            patch("dex_studio.store.get_store", MagicMock()),
        ):
            scheduler_clear_dead_letter(eng, "stuck_pipeline")

        assert jobs_mod.is_pipeline_running("stuck_pipeline"), (
            "Regression: after clear_dead_letter, pipeline must be in _running set"
        )

    def test_dead_letter_state_fully_cleared_in_db(self, tmp_path: Path) -> None:
        """Both dead-letter record AND run-state (retry counter) are reset."""
        from datetime import UTC, datetime, timedelta

        studio_db = StudioDb(tmp_path / "studio.db")
        # Seed dead letter + retry state
        studio_db.record_dead_letter("stuck_pipeline", "connection timeout", attempts=3)
        studio_db.mark_dead("stuck_pipeline")
        retry_at = datetime.now(UTC) + timedelta(seconds=300)
        studio_db.increment_attempts("stuck_pipeline", retry_at)

        eng = MagicMock()
        eng.config_path = None

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=studio_db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started"),
        ):
            scheduler_clear_dead_letter(eng, "stuck_pipeline")

        # Dead letter record gone
        dead = studio_db.get_dead_letter()
        assert not any(d["pipeline"] == "stuck_pipeline" for d in dead), (
            "Dead letter record must be removed"
        )
        # Retry counter reset
        state = studio_db.get_run_state("stuck_pipeline")
        assert state["attempts"] == 0, "Retry counter must be reset to 0"


# ── Bug 3 regression ──────────────────────────────────────────────────────────


class TestBug3SecopsRoutes404:
    """Regression: /secops/privacy and /secops/policies must return HTTP 200."""

    def test_secops_privacy_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/privacy")
        assert resp.status_code == 200, (
            f"Regression: /secops/privacy returned {resp.status_code}, expected 200"
        )

    def test_secops_policies_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/policies")
        assert resp.status_code == 200, (
            f"Regression: /secops/policies returned {resp.status_code}, expected 200"
        )

    def test_secops_privacy_renders_html(self, authed_client: TestClient) -> None:
        """Response must be HTML — confirms template was found and rendered."""
        resp = authed_client.get("/secops/privacy")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML response, got: {content_type}"

    def test_secops_policies_renders_html(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/policies")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, f"Expected HTML response, got: {content_type}"

    def test_secops_overview_still_works(self, authed_client: TestClient) -> None:
        """Verify that existing /secops/ route was not broken by the addition of new routes."""
        resp = authed_client.get("/secops/")
        assert resp.status_code == 200

    def test_secops_audit_still_works(self, authed_client: TestClient) -> None:
        """Verify that existing /secops/audit route was not broken."""
        resp = authed_client.get("/secops/audit")
        assert resp.status_code == 200

    def test_unauthenticated_privacy_redirects_to_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """New routes must be auth-protected — not public pages."""
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=_hash_password(_API_KEY))
        mock_eng = _make_engine_mock()
        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from importlib import import_module

            # Force fresh app creation for this test
            app_mod = import_module("dex_studio.app")
            app = app_mod.create_app()
            unauthed = TestClient(app, follow_redirects=False)

        resp = unauthed.get("/secops/privacy")
        assert resp.status_code in (302, 303), (
            "/secops/privacy must redirect unauthenticated users to login"
        )
        assert "/login" in resp.headers.get("location", "")

    def test_unauthenticated_policies_redirects_to_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=_hash_password(_API_KEY))
        mock_eng = _make_engine_mock()
        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from importlib import import_module

            app_mod = import_module("dex_studio.app")
            app = app_mod.create_app()
            unauthed = TestClient(app, follow_redirects=False)

        resp = unauthed.get("/secops/policies")
        assert resp.status_code in (302, 303), (
            "/secops/policies must redirect unauthenticated users to login"
        )
        assert "/login" in resp.headers.get("location", "")
