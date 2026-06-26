"""Integration tests for /api/* JSON REST endpoints.

Tests that JSON API endpoints return valid responses with correct status
codes, content types, and enforce authentication.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password, clear_rate_limit

_API_KEY = "test-api-key-1234"  # gitleaks:allow
_SESSION_SECRET = "t" * 32


def _make_engine_mock() -> MagicMock:
    eng = MagicMock()
    eng.config_path = "/tmp/test.yaml"
    eng.config.project = SimpleNamespace(name="TestProject")
    # Use real objects for config.data so .pipelines.items() works
    eng.config.data = SimpleNamespace(
        sources={},
        pipelines={
            "clean_users": SimpleNamespace(
                schedule="0 * * * *",
                source="users",
                destination="silver.users",
            ),
        },
    )
    eng.config.ai = MagicMock()
    eng.config.ai.agents = {}
    eng.agents = {}
    eng.pipeline_stats.return_value = {"total": 1, "scheduled": 1, "failed": 0, "running": 0}
    eng.health.return_value = {"status": "ok", "components": {}}
    eng.model_registry.list_models.return_value = []
    eng.warehouse_layers.return_value = []
    eng.warehouse_tables.return_value = []
    eng.store.get_pipeline_runs.return_value = []
    eng.store.list_model_artifacts.return_value = []
    eng.store.list_experiments.return_value = []
    eng.store.lineage_summary.return_value = {}
    eng.store.get_memory.return_value = []
    eng.ai_memory = None
    eng.ai_long_memory = None
    eng.ai_episodic = None
    eng.ai_audit = None
    eng.ai_metrics = None
    eng.pipeline_last_run.return_value = None
    return eng


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        client = TestClient(app, follow_redirects=False)
        clear_rate_limit("test")
        resp = client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303), f"login failed: {resp.status_code}"
        yield client


@pytest.fixture
def csrf_headers(authed_client: TestClient) -> dict[str, str]:
    r = authed_client.get("/data/sources")
    match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', r.content)
    assert match, "CSRF meta tag not found"
    return {"X-CSRF-Token": match.group(1).decode()}


@pytest.fixture
def unauthed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    hash_file = tmp_path / "auth_unauthed.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        yield TestClient(app, follow_redirects=False)


class TestApiScheduler:
    def test_status_returns_json(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/api/scheduler/status")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        body = resp.json()
        assert "enabled" in body
        assert "paused" in body

    def test_pause_resume_cycle(
        self, authed_client: TestClient, csrf_headers: dict[str, str]
    ) -> None:
        resp = authed_client.post("/api/scheduler/pause", headers=csrf_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
        resp = authed_client.post("/api/scheduler/resume", headers=csrf_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "resumed"


class TestApiPipelines:
    def test_list_pipelines(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/api/pipelines")
        assert resp.status_code == 200, f"body: {resp.text[:500]}"
        assert resp.headers["content-type"] == "application/json"
        body = resp.json()
        assert isinstance(body, list), f"expected list, got {type(body)}: {body!r}"
        assert len(body) > 0, f"empty pipeline list, body={body!r}"
        names = [p["name"] for p in body]
        assert "clean_users" in names, f"clean_users not in {names}"

    def test_pipeline_run(self, authed_client: TestClient, csrf_headers: dict[str, str]) -> None:
        resp = authed_client.post("/api/pipelines/clean_users/run", headers=csrf_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("success", "error")


class TestApiAlerts:
    def test_list_alerts(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/api/alerts")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert isinstance(resp.json(), list)

    def test_quality_contracts(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/api/quality/contracts")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert isinstance(resp.json(), list)


class TestApiWatermarks:
    def test_list_watermarks(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/api/watermarks")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert isinstance(resp.json(), list)


class TestApiCompaction:
    def test_compaction_status(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/api/compaction/status")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert isinstance(resp.json(), list)


class TestApiAuthEnforcement:
    _API_ROUTES = [
        "/api/scheduler/status",
        "/api/pipelines",
        "/api/alerts",
        "/api/watermarks",
        "/api/compaction/status",
        "/api/quality/contracts",
    ]

    @pytest.mark.parametrize("path", _API_ROUTES)
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient, path: str) -> None:
        resp = unauthed_client.get(path)
        assert resp.status_code in (401, 302, 303), (
            f"Expected 401/redirect for {path}, got {resp.status_code}"
        )
