"""Tests for FastAPI auth Depends — ReadDep, JsonReadDep, WriteDep, WebSocket auth."""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password

_API_KEY = "test-api-key-1234"  # gitleaks:allow
_SESSION_SECRET = "t" * 32


def _make_engine_mock() -> MagicMock:
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
def unauthed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Client with API key set but no session — every request is unauthenticated."""
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        yield TestClient(app, follow_redirects=False)


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Client with a valid session (logged in via POST /login)."""
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303), f"login failed: {resp.status_code}"
        yield client


# ── HTML route auth (ReadDep) ─────────────────────────────────────────────────


class TestHtmlAuthDep:
    def test_unauthenticated_hub_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_unauthenticated_data_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/data/pipelines")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_unauthenticated_intelligence_redirects_to_login(
        self, unauthed_client: TestClient
    ) -> None:
        resp = unauthed_client.get("/intelligence/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_unauthenticated_intelligence_playground_redirects_to_login(
        self, unauthed_client: TestClient
    ) -> None:
        resp = unauthed_client.get("/intelligence/playground")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_unauthenticated_secops_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/secops/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_unauthenticated_system_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/system/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_authenticated_hub_renders(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/")
        assert resp.status_code == 200

    def test_public_routes_never_redirect(self, unauthed_client: TestClient) -> None:
        for path in ("/login", "/onboarding"):
            resp = unauthed_client.get(path)
            assert resp.status_code == 200, f"{path} should be public"


# ── JSON route auth (JsonReadDep) ─────────────────────────────────────────────


class TestJsonAuthDep:
    def test_unauthenticated_pipeline_runs_all_returns_401(
        self, unauthed_client: TestClient
    ) -> None:
        resp = unauthed_client.get("/data/pipelines/runs/all")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unauthorized"

    def test_unauthenticated_pipeline_runs_for_returns_401(
        self, unauthed_client: TestClient
    ) -> None:
        resp = unauthed_client.get("/data/pipelines/my-pipe/runs")
        assert resp.status_code == 401

    def test_unauthenticated_predict_models_returns_401(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/intelligence/predict/models")
        assert resp.status_code == 401

    def test_unauthenticated_chat_returns_401(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.post("/intelligence/chat", json={"agent": "bot", "message": "hi"})
        assert resp.status_code == 401

    def test_unauthenticated_native_call_returns_401(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.post("/intelligence/native", json={"tool": "noop"})
        assert resp.status_code == 401

    def test_unauthenticated_chat_stream_returns_401(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/intelligence/stream?agent=bot&message=hi")
        assert resp.status_code == 401

    def test_authenticated_pipeline_runs_all_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/data/pipelines/runs/all")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ── CSRF enforcement (WriteDep) ───────────────────────────────────────────────


def _extract_csrf(html: str) -> str:
    """Parse CSRF token from <meta name="csrf-token" content="...">."""
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


class TestCSRFEnforcement:
    def test_post_without_csrf_after_token_set_returns_403(self, authed_client: TestClient) -> None:
        # GET /intelligence/agents sets the CSRF token in the session via base_ctx.
        resp = authed_client.get("/intelligence/agents")
        assert resp.status_code == 200
        # POST with no CSRF header/param → 403.
        resp = authed_client.post("/intelligence/agents/add", data={"name": "x"})
        assert resp.status_code == 403

    def test_post_with_csrf_header_succeeds(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/intelligence/agents")
        csrf = _extract_csrf(resp.text)
        assert csrf, "CSRF token not found in page HTML"
        resp = authed_client.post(
            "/intelligence/agents/add",
            data={"name": "bot", "runtime": "builtin"},
            headers={"X-CSRF-Token": csrf},
        )
        # Redirect after successful POST-redirect-get, or 200 if inline.
        assert resp.status_code in (200, 302, 303)

    def test_post_with_wrong_csrf_returns_403(self, authed_client: TestClient) -> None:
        authed_client.get("/intelligence/agents")  # set CSRF in session
        resp = authed_client.post(
            "/intelligence/agents/add",
            data={"name": "bot"},
            headers={"X-CSRF-Token": "definitely-wrong"},
        )
        assert resp.status_code == 403

    def test_post_without_csrf_token_returns_403(self, authed_client: TestClient) -> None:
        # CSRF is seeded at login — every authenticated POST requires the token.
        resp = authed_client.post("/intelligence/agents/add", data={"name": "bot"})
        assert resp.status_code == 403


# ── WebSocket auth ────────────────────────────────────────────────────────────


class TestWebSocketAuth:
    def test_unauthenticated_websocket_closes_with_3000(self, unauthed_client: TestClient) -> None:
        from starlette.websockets import WebSocketDisconnect

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            unauthed_client.websocket_connect("/intelligence/playground/ws/test-agent") as ws,
        ):
            ws.receive_text()
        assert exc_info.value.code == 3000

    def test_authenticated_websocket_accepts(self, authed_client: TestClient) -> None:
        # Authenticated WS should accept and stay open until we disconnect.
        with authed_client.websocket_connect("/intelligence/playground/ws/unknown-agent") as ws:
            ws.send_text("hello")
            data = ws.receive_json()
        # Unknown agent → assistant error reply, not a close.
        assert "content" in data
