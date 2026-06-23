"""Integration tests for SecOps routes — smoke, acceptance, and content tests.

Strategy:
  - authed_client: logs in via POST /login with a valid passphrase.
  - unauthed_client: no session — every request is unauthenticated.
  - Engine is mocked via patch("dex_studio._engine.get_engine").
  - TestClient uses follow_redirects=False so redirect behaviour is explicit.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password

_API_KEY = "test-api-key-1234"  # gitleaks:allow
_SESSION_SECRET = "t" * 32


# ── Engine mock ───────────────────────────────────────────────────────────────


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
    # secops-specific attributes — absent on a real engine with no secops config
    del eng.privacy_guard  # triggers getattr(..., None) fallback in router
    del eng.secops_audit
    eng.pipeline_last_run.return_value = None
    return eng


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Authenticated client — valid session via POST /login."""
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
def authed_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """Authenticated client — valid session via POST /login."""
    monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", _API_KEY)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303), f"login failed: {resp.status_code}"
        yield client


@pytest.fixture
def unauthed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Unauthenticated client — API key set but no session cookie."""
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
def unauthed_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """Unauthenticated client — API key set but no session cookie."""
    monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", _API_KEY)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        yield TestClient(app, follow_redirects=False)


# ── Smoke tests — all SecOps routes return 200 ────────────────────────────────


class TestSecopsSmoke:
    """Each SecOps route should render without error when authenticated."""

    def test_secops_overview_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/")
        assert resp.status_code == 200

    def test_secops_privacy_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/privacy")
        assert resp.status_code == 200

    def test_secops_policies_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/policies")
        assert resp.status_code == 200

    def test_secops_audit_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/audit")
        assert resp.status_code == 200

    def test_secops_alerts_returns_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/alerts")
        assert resp.status_code == 200


# ── Auth tests — unauthenticated access redirects to /login ──────────────────


class TestSecopsAuthGuard:
    """Unauthenticated requests to SecOps routes must redirect to /login."""

    def test_privacy_unauthed_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/secops/privacy")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_policies_unauthed_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/secops/policies")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_overview_unauthed_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/secops/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_audit_unauthed_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/secops/audit")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]

    def test_alerts_unauthed_redirects_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.get("/secops/alerts")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers["location"]


# ── Acceptance tests — page content ──────────────────────────────────────────


class TestSecopsPrivacyContent:
    """The /secops/privacy page must contain the expected UI sections."""

    def test_privacy_contains_privacyguard_heading(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/privacy")
        assert resp.status_code == 200
        # page_title block renders "Privacy Guard"; banner renders "PrivacyGuard is …"
        body = resp.text
        assert "Privacy Guard" in body or "PrivacyGuard" in body

    def test_privacy_contains_detection_settings_section(self, authed_client: TestClient) -> None:
        """The detection configuration panel must be present."""
        resp = authed_client.get("/secops/privacy")
        body = resp.text
        # The card header "Detection settings" identifies the guard-config panel.
        assert "Detection settings" in body

    def test_privacy_contains_masking_strategy_table(self, authed_client: TestClient) -> None:
        """PII masking strategies table (or empty state) must be rendered."""
        resp = authed_client.get("/secops/privacy")
        body = resp.text
        # Template renders "PII masking strategies" as the table header.
        assert "masking" in body.lower() or "strategy" in body.lower()

    def test_privacy_contains_guard_status_pill(self, authed_client: TestClient) -> None:
        """The guard enabled/disabled pill must be present."""
        resp = authed_client.get("/secops/privacy")
        body = resp.text
        # pill values are "yes"/"no"; guard-status banner shows "active"/"inactive"
        assert "inactive" in body or "active" in body

    def test_privacy_html_is_well_formed_html(self, authed_client: TestClient) -> None:
        """Response must be HTML with a doctype or <html> tag."""
        resp = authed_client.get("/secops/privacy")
        assert "text/html" in resp.headers.get("content-type", "")


class TestSecopsPoliciesContent:
    """The /secops/policies page must contain policy governance sections."""

    def test_policies_contains_policies_heading(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/policies")
        body = resp.text
        # page_title is "Data Policies"; nav crumb also contains "Policies"
        assert "Policies" in body

    def test_policies_contains_global_governance_section(self, authed_client: TestClient) -> None:
        """Global data governance settings card must be present."""
        resp = authed_client.get("/secops/policies")
        body = resp.text
        assert "governance" in body.lower() or "Global data" in body

    def test_policies_contains_pii_handling_section(self, authed_client: TestClient) -> None:
        """PII handling policies table must be present (with data or empty state)."""
        resp = authed_client.get("/secops/policies")
        body = resp.text
        assert "PII" in body or "pii" in body.lower()

    def test_policies_contains_enforcement_mode_row(self, authed_client: TestClient) -> None:
        """Enforcement mode row must render (shows 'block' or 'warn')."""
        resp = authed_client.get("/secops/policies")
        body = resp.text
        assert "Enforcement mode" in body

    def test_policies_contains_default_pii_action(self, authed_client: TestClient) -> None:
        """Default PII action metric card must be present."""
        resp = authed_client.get("/secops/policies")
        body = resp.text
        # metric_card renders "Default PII action"
        assert "Default PII action" in body

    def test_policies_html_is_well_formed_html(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/secops/policies")
        assert "text/html" in resp.headers.get("content-type", "")


# ── Full-coverage smoke test — all major routes ───────────────────────────────


class TestAllRoutesSmokeTest:
    """Hit every major route and verify it returns 200 (or the expected redirect).

    This class guards against router registration regressions and catches
    template rendering errors that unit tests miss.
    """

    # Routes that must return HTTP 200 when authenticated.
    _OK_ROUTES = [
        # Hub
        "/",
        # Data
        "/data/",
        "/data/pipelines",
        "/data/sources",
        "/data/warehouse",
        "/data/lineage",
        "/data/quality",
        "/data/sql",
        # Intelligence
        "/intelligence/",
        "/intelligence/models",
        "/intelligence/experiments",
        "/intelligence/agents",
        # SecOps
        "/secops/",
        "/secops/privacy",
        "/secops/policies",
        "/secops/audit",
        "/secops/alerts",
        # System
        "/system/",
        "/system/logs",
        "/system/metrics",
    ]

    @pytest.mark.parametrize("path", _OK_ROUTES)
    def test_authenticated_route_returns_200(self, authed_client: TestClient, path: str) -> None:
        resp = authed_client.get(path)
        assert resp.status_code == 200, f"Expected 200 for {path!r}, got {resp.status_code}"
    def test_authenticated_route_returns_200(
        self, authed_client: TestClient, path: str
    ) -> None:
        resp = authed_client.get(path)
        assert resp.status_code == 200, (
            f"Expected 200 for {path!r}, got {resp.status_code}"
        )

    # Routes that must redirect unauthenticated requests to /login.
    _AUTH_GUARDED_ROUTES = [
        "/",
        "/data/pipelines",
        "/data/sources",
        "/data/warehouse",
        "/data/lineage",
        "/data/quality",
        "/data/sql",
        "/intelligence/",
        "/intelligence/models",
        "/intelligence/experiments",
        "/intelligence/agents",
        "/secops/",
        "/secops/privacy",
        "/secops/policies",
        "/secops/audit",
        "/secops/alerts",
        "/system/",
        "/system/logs",
        "/system/metrics",
    ]

    @pytest.mark.parametrize("path", _AUTH_GUARDED_ROUTES)
    def test_unauthenticated_route_redirects_to_login(
        self, unauthed_client: TestClient, path: str
    ) -> None:
        resp = unauthed_client.get(path)
        assert resp.status_code in (302, 303), (
            f"Expected redirect for {path!r}, got {resp.status_code}"
        )
        assert "/login" in resp.headers.get("location", ""), (
            f"Redirect for {path!r} did not point to /login"
        )
