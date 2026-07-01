"""Integration tests for the full auth lifecycle.

Covers the complete flow: first boot → setup → login → session →
logout → reset → re-setup → re-login.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password, clear_rate_limit

_API_KEY = "test-api-key-1234"  # gitleaks:allow
_SESSION_SECRET = "t" * 32


def _patch_db(monkeypatch: pytest.MonkeyPatch, *, return_hash: str | None = None) -> None:
    monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=return_hash))
    monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
    monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())


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
def no_password_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """Client with no password set — first-boot state."""
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    _patch_db(monkeypatch, return_hash=None)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        yield TestClient(app, follow_redirects=False)


@pytest.fixture
def password_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """Client with a pre-set password but not yet logged in."""
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    _patch_db(monkeypatch, return_hash=_hash_password(_API_KEY))
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        yield TestClient(app, follow_redirects=False)


@pytest.fixture
def authed_client(password_client: TestClient) -> Generator[TestClient]:
    """Pre-authenticated client — logged in with valid credentials."""
    clear_rate_limit("test")
    resp = password_client.post("/login", data={"passphrase": _API_KEY})
    assert resp.status_code in (302, 303), f"login failed: {resp.status_code}"
    yield password_client


# ── First boot / setup ────────────────────────────────────────────────────


class TestFirstBoot:
    """No password configured — should redirect to /setup."""

    def test_root_redirects_to_setup(self, no_password_client: TestClient) -> None:
        resp = no_password_client.get("/")
        assert resp.status_code in (302, 303)
        assert "/setup" in resp.headers["location"]

    def test_login_redirects_to_setup(self, no_password_client: TestClient) -> None:
        resp = no_password_client.get("/login")
        assert resp.status_code in (302, 303)
        assert "/setup" in resp.headers["location"]

    def test_setup_page_renders(self, no_password_client: TestClient) -> None:
        resp = no_password_client.get("/setup")
        assert resp.status_code == 200
        assert b"passphrase" in resp.content.lower() or b"password" in resp.content.lower()

    def test_setup_rejects_short_password(self, no_password_client: TestClient) -> None:
        resp = no_password_client.post("/setup", data={"password": "ab"})
        assert resp.status_code == 200
        assert b"8" in resp.content or b"short" in resp.content.lower()

    def test_setup_creates_password(self, no_password_client: TestClient) -> None:
        resp = no_password_client.post("/setup", data={"password": _API_KEY})
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]


# ── Login / logout ────────────────────────────────────────────────────────


class TestLoginLogout:
    """Password exists — full login/logout flow."""

    def test_login_page_renders(self, password_client: TestClient) -> None:
        resp = password_client.get("/login")
        assert resp.status_code == 200
        assert b"passphrase" in resp.content.lower() or b"password" in resp.content.lower()

    def test_setup_redirects_to_login(self, password_client: TestClient) -> None:
        resp = password_client.get("/setup")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_login_with_correct_password(self, password_client: TestClient) -> None:
        clear_rate_limit("test")
        resp = password_client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303)
        assert resp.headers["location"] in ("/", "http://testserver/")

    def test_login_with_wrong_password(self, password_client: TestClient) -> None:
        clear_rate_limit("test")
        resp = password_client.post("/login", data={"passphrase": "wrong-password"})
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_authenticated_session_persists(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/")
        assert resp.status_code == 200

    def test_logout_clears_session(self, authed_client: TestClient) -> None:
        # Seed CSRF token via a GET request
        get_resp = authed_client.get("/")
        csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', get_resp.content)
        headers = {"X-CSRF-Token": csrf.group(1).decode()} if csrf else {}
        resp = authed_client.post("/logout", headers=headers)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]
        resp2 = authed_client.get("/")
        assert resp2.status_code in (302, 303)
        assert "/login" in resp2.headers["location"]

    def test_login_then_access_protected_routes(self, password_client: TestClient) -> None:
        clear_rate_limit("test")
        password_client.post("/login", data={"passphrase": _API_KEY})
        for path in ("/data/pipelines", "/data/sources", "/system/logs"):
            resp = password_client.get(path)
            assert resp.status_code == 200, f"Expected 200 for {path}"


# ── Reset flow ────────────────────────────────────────────────────────────


class TestResetFlow:
    """Password reset via reset_password + setup flow."""

    def test_setup_redirects_to_login_when_password_exists(
        self, authed_client: TestClient
    ) -> None:
        resp = authed_client.get("/setup")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_setup_shows_page_after_reset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=None)
        mock_eng = _make_engine_mock()
        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app, follow_redirects=False)
            resp = client.get("/setup")
            assert resp.status_code == 200
            assert b"passphrase" in resp.content.lower() or b"password" in resp.content.lower()

    def test_old_login_fails_when_no_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=None)
        mock_eng = _make_engine_mock()
        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app, follow_redirects=False)
            resp = client.post("/login", data={"passphrase": _API_KEY})
            assert resp.status_code in (302, 303)
            assert resp.headers.get("location", "") in ("/login", "/setup")

    def test_setup_after_reset_creates_new_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stored: dict[str, str] = {}
        monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: stored.get(k))
        monkeypatch.setattr(
            "dex_studio.db_store.set_setting", lambda k, v: stored.__setitem__(k, v)
        )
        monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
        monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        mock_eng = _make_engine_mock()
        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app, follow_redirects=False)
            new_key = "new-password-4567"
            resp = client.post("/setup", data={"password": new_key})
            assert resp.status_code in (302, 303)
            assert resp.headers["location"] in ("/login", "/")
            clear_rate_limit("test")
            resp2 = client.post("/login", data={"passphrase": new_key})
            assert resp2.status_code in (302, 303)
            assert resp2.headers["location"] in ("/", "http://testserver/", "http://localhost/")
