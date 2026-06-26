"""Security tests for DEX Studio — auth bypass, CSRF, session, injection."""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password

_API_KEY = "test-security-key-xyz"  # gitleaks:allow
_SESSION_SECRET = "s" * 32


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
    eng.source_stats.return_value = {"row_count": 0, "column_count": 0}
    eng.source_schema.return_value = []
    eng.source_sample.return_value = []
    eng.health.return_value = {"status": "ok", "components": {}}
    eng.model_registry.list_models.return_value = []
    eng.warehouse_layers.return_value = []
    eng.warehouse_tables.return_value = []
    eng.store.get_pipeline_runs.return_value = []
    eng.store.list_model_artifacts.return_value = []
    eng.store.list_experiments.return_value = []
    eng.store.lineage_summary.return_value = {
        "total_events": 0,
        "by_layer": {},
        "by_operation": {},
    }
    eng.store.get_memory.return_value = []
    eng.pipeline_last_run.return_value = None
    eng.ai_memory = None
    eng.ai_long_memory = None
    eng.ai_episodic = None
    eng.ai_audit = None
    eng.ai_metrics = None
    return eng


def _reset_rate_limiter() -> None:
    """Clear the module-level rate-limiter singleton between tests.

    The limiter is a module-level object in dex_studio.auth; its failure
    history persists across test functions unless explicitly cleared.
    Tests that submit wrong passwords (TestBruteForce) would otherwise
    trigger the lockout and cause every subsequent fixture login to fail.
    """
    import dex_studio.auth as _auth

    with _auth._limiter._lock:
        _auth._limiter._failures.clear()


@pytest.fixture
def unauthed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Client with API key set but no session — every request is unauthenticated."""
    _reset_rate_limiter()
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
def unauthed_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """Client with API key set but no session — every request is unauthenticated."""
    _reset_rate_limiter()
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        yield TestClient(app, follow_redirects=False)
    _reset_rate_limiter()


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Client with a valid session (logged in via POST /login)."""
    _reset_rate_limiter()
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
def authed_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """Client with a valid session (logged in via POST /login)."""
    _reset_rate_limiter()
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
    _reset_rate_limiter()


def _extract_csrf(html: str) -> str:
    """Parse CSRF token from <meta name="csrf-token" content="...">."""
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


# ── Auth bypass ───────────────────────────────────────────────────────────────


class TestAuthBypass:
    """Direct access to protected routes without a session must redirect to /login."""

    _PROTECTED_ROUTES = [
        "/",
        "/data/pipelines",
        "/data/sources",
        "/data/sql",
        "/data/warehouse",
        "/data/lineage",
        "/data/catalog",
        "/data/quality",
        "/secops/",
        "/system/",
        "/intelligence/agents",
    ]

    @pytest.mark.parametrize("path", _PROTECTED_ROUTES)
    def test_protected_route_redirects_to_login(
        self, unauthed_client: TestClient, path: str
    ) -> None:
        resp = unauthed_client.get(path)
        assert resp.status_code in (302, 303), f"{path} should redirect, got {resp.status_code}"
        assert "/login" in resp.headers.get("location", ""), (
            f"{path} redirect should go to /login, got {resp.headers.get('location')}"
        )

    def test_hub_authenticated_renders_200(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/")
        assert resp.status_code == 200


# ── Session fixation ──────────────────────────────────────────────────────────


class TestSessionFixation:
    """Login with a valid key should establish a session that persists across requests."""

    def test_login_sets_authenticated_session(self, unauthed_client: TestClient) -> None:
        # Before login, hub is inaccessible.
        resp = unauthed_client.get("/")
        assert resp.status_code in (302, 303)

        # Log in.
        resp = unauthed_client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303)

        # After login, hub is accessible.
        resp = unauthed_client.get("/")
        assert resp.status_code == 200

    def test_logout_clears_session(self, authed_client: TestClient) -> None:
        # Confirm we're authenticated.
        resp = authed_client.get("/")
        assert resp.status_code == 200

        # Log out.
        resp = authed_client.get("/logout")
        assert resp.status_code in (302, 303)

        # Hub should now redirect to login again.
        resp = authed_client.get("/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_session_persists_across_multiple_requests(self, authed_client: TestClient) -> None:
        """Multiple requests in the same session stay authenticated."""
        for _ in range(3):
            resp = authed_client.get("/")
            assert resp.status_code == 200


# ── Brute force / rate limiting ───────────────────────────────────────────────


class TestBruteForce:
    """Wrong passwords should return the login page (not 200 on a protected resource)."""

    def test_wrong_password_returns_redirect_to_login(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.post("/login", data={"passphrase": "wrong-password"})
        # Should redirect back to /login (not grant access).
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_wrong_password_three_times_stays_at_login(self, unauthed_client: TestClient) -> None:
    def test_wrong_password_three_times_stays_at_login(
        self, unauthed_client: TestClient
    ) -> None:
        for _ in range(3):
            resp = unauthed_client.post("/login", data={"passphrase": "bad-attempt"})
            assert resp.status_code in (302, 303)
            assert "/login" in resp.headers.get("location", "")

        # Still cannot access protected resource.
        resp = unauthed_client.get("/")
        assert resp.status_code in (302, 303)

    def test_empty_password_does_not_grant_access(self, unauthed_client: TestClient) -> None:
        # FastAPI rejects a blank required Form field with 422 before the route
        # runs, so it never reaches auth logic — that is also acceptable since
        # the request is definitively rejected and no session is granted.
        resp = unauthed_client.post("/login", data={"passphrase": ""})
        assert resp.status_code in (302, 303, 422), (
            f"Empty passphrase should be rejected, got {resp.status_code}"
        )

        # Regardless of how the POST was rejected, the hub is still inaccessible.
        resp2 = unauthed_client.get("/")
        assert resp2.status_code in (302, 303)


# ── Passphrase timing safety ──────────────────────────────────────────────────


class TestPassphraseTiming:
    """Wrong password must return the login-page redirect, not a server error.

    hmac.compare_digest is used internally; we verify the observable behaviour
    (wrong → redirect to /login) rather than measuring wall-clock time, which
    is unreliable in test environments.
    """

    def test_wrong_password_returns_login_redirect(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.post("/login", data={"passphrase": "definitely-wrong"})
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_correct_password_redirects_to_hub(self, unauthed_client: TestClient) -> None:
        resp = unauthed_client.post("/login", data={"passphrase": _API_KEY})
        assert resp.status_code in (302, 303)
        # On success the redirect must NOT go back to /login.
        location = resp.headers.get("location", "")
        assert "/login" not in location, (
            f"Successful login should redirect to hub, not /login; got {location!r}"
        )


# ── CSRF bypass ───────────────────────────────────────────────────────────────


class TestCSRFBypass:
    """POST to protected routes without a valid CSRF token must return 403."""

    def test_post_without_csrf_token_returns_403(self, authed_client: TestClient) -> None:
        # Seed the CSRF token in the session via a GET first.
        authed_client.get("/intelligence/agents")
        resp = authed_client.post("/intelligence/agents/add", data={"name": "bot"})
        assert resp.status_code == 403

    def test_post_with_wrong_csrf_token_returns_403(self, authed_client: TestClient) -> None:
        authed_client.get("/intelligence/agents")
        resp = authed_client.post(
            "/intelligence/agents/add",
            data={"name": "bot"},
            headers={"X-CSRF-Token": "totally-wrong-token"},
        )
        assert resp.status_code == 403

    def test_post_with_correct_csrf_header_succeeds(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/intelligence/agents")
        csrf = _extract_csrf(resp.text)
        assert csrf, "CSRF token not found in page HTML"

        resp = authed_client.post(
            "/intelligence/agents/add",
            data={"name": "mybot", "runtime": "builtin"},
            headers={"X-CSRF-Token": csrf},
        )
        # Success: redirect after PRG, or 200 if inline.
        assert resp.status_code in (200, 302, 303)

    def test_post_data_pipeline_without_csrf_returns_403(self, authed_client: TestClient) -> None:
        """Data domain POST route also rejects missing CSRF."""
        authed_client.get("/data/pipelines")
        resp = authed_client.post(
            "/data/pipelines/add",
            data={"name": "pipe1", "source": "src"},
        )
        assert resp.status_code == 403


# ── CSRF token rotation ───────────────────────────────────────────────────────


class TestCSRFTokenRotation:
    """Token must be consistent within a session (not per-request), but present."""

    def test_csrf_token_present_in_page(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/")
        csrf = _extract_csrf(resp.text)
        assert csrf, "CSRF token should be present in the hub page"

    def test_csrf_token_same_across_two_gets(self, authed_client: TestClient) -> None:
        """Two GET requests in the same session should return the same CSRF token."""
        resp1 = authed_client.get("/")
        resp2 = authed_client.get("/data/pipelines")
        token1 = _extract_csrf(resp1.text)
        token2 = _extract_csrf(resp2.text)
        assert token1 and token2, "Both pages must embed the CSRF token"
        assert token1 == token2, (
            f"CSRF token must be stable within a session; got {token1!r} then {token2!r}"
            "CSRF token must be stable within a session; "
            f"got {token1!r} then {token2!r}"
        )

    def test_csrf_token_nonempty_and_hex(self, authed_client: TestClient) -> None:
        resp = authed_client.get("/")
        csrf = _extract_csrf(resp.text)
        assert csrf, "CSRF token must not be empty"
        # token_hex(24) → 48 hex chars
        assert re.fullmatch(r"[0-9a-f]+", csrf), f"Expected hex token, got {csrf!r}"
        assert len(csrf) >= 32, f"CSRF token too short: {len(csrf)} chars"


# ── Cookie security ───────────────────────────────────────────────────────────


class TestCookieSecurity:
    """Session cookie attributes after login."""

    def _get_session_cookie(self, client: TestClient) -> str:
        """Return the raw Set-Cookie header from a login response."""
        resp = client.post("/login", data={"passphrase": _API_KEY})
        return resp.headers.get("set-cookie", "")

    def test_session_cookie_is_set_after_login(self, unauthed_client: TestClient) -> None:
    def test_session_cookie_is_set_after_login(
        self, unauthed_client: TestClient
    ) -> None:
        cookie = self._get_session_cookie(unauthed_client)
        assert cookie, "Set-Cookie header must be present after login"

    def test_session_cookie_has_httponly(self, unauthed_client: TestClient) -> None:
        cookie = self._get_session_cookie(unauthed_client)
        assert "httponly" in cookie.lower(), (
            f"Session cookie must have HttpOnly attribute; got: {cookie}"
        )

    def test_session_cookie_has_samesite(self, unauthed_client: TestClient) -> None:
        cookie = self._get_session_cookie(unauthed_client)
        assert "samesite" in cookie.lower(), (
            f"Session cookie must have SameSite attribute; got: {cookie}"
        )


# ── Path traversal ────────────────────────────────────────────────────────────


class TestPathTraversal:
    """Path traversal attempts must not return 200 with file contents."""

    @pytest.mark.parametrize(
        "path",
        [
            "/data/sources/../../../etc/passwd",
            "/data/pipelines/../../etc/shadow",
            "/data/catalog/../../../../etc/hosts",
        ],
    )
    def test_path_traversal_not_200(self, authed_client: TestClient, path: str) -> None:
        resp = authed_client.get(path)
        # Any response except 200 is acceptable — must not silently serve files.
        assert resp.status_code != 200, (
            f"Path traversal {path!r} should not return 200, got {resp.status_code}"
        )

    @pytest.mark.parametrize(
        "path",
        [
            "/data/sources/../../../etc/passwd",
            "/data/pipelines/../../etc/shadow",
        ],
    )
    def test_path_traversal_returns_4xx(self, unauthed_client: TestClient, path: str) -> None:
        """Unauthenticated traversal attempts must not 200 either."""
        resp = unauthed_client.get(path)
        # Redirect (302/303) or 4xx — anything but 200.
        assert resp.status_code != 200


# ── SQL injection in query params ─────────────────────────────────────────────


class TestSQLInjection:
    """Malicious query strings must not crash the server (no 500)."""

    _INJECTIONS = [
        "'; DROP TABLE users; --",
        "1 OR 1=1",
        '" OR ""="',
        "\" OR \"\"=\"",
        "1; SELECT * FROM information_schema.tables",
        "' UNION SELECT NULL, NULL --",
    ]

    @pytest.mark.parametrize("payload", _INJECTIONS)
    def test_sql_execute_injection_no_server_error(
        self, unauthed_client: TestClient, payload: str
    ) -> None:
        """Unauthenticated SQL injection attempt must not return 500."""
        resp = unauthed_client.get(f"/data/sql/execute?query={payload}")
        # Without auth this will be 302/303/401; never 500.
        assert resp.status_code != 500, (
            f"Server error on SQL injection payload {payload!r}: {resp.status_code}"
        )

    @pytest.mark.parametrize("payload", _INJECTIONS)
    def test_sql_injection_no_server_error_authenticated(
        self, authed_client: TestClient, payload: str
    ) -> None:
        """Authenticated SQL injection attempt must not crash (200 or 400, not 500)."""
        import urllib.parse

        encoded = urllib.parse.quote(payload, safe="")
        resp = authed_client.get(f"/data/sql?q={encoded}")
        assert resp.status_code != 500, (
            f"Authenticated SQL injection caused server error for {payload!r}"
        )


# ── XSS in rendered content ───────────────────────────────────────────────────


class TestXSSEscaping:
    """Jinja2 autoescapes by default — injected script tags must not appear raw in HTML."""

    def test_xss_pipeline_name_escaped_in_response(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hash_file = tmp_path / "auth.hash"
        hash_file.write_text(_hash_password(_API_KEY))
        monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hash_file = tmp_path / "auth.hash"
        hash_file.write_text(_hash_password(_API_KEY))
        monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)

        xss_name = "<script>alert(1)</script>"
        mock_eng = _make_engine_mock()
        # Inject an XSS payload as a pipeline name in the engine config.
        mock_eng.config.data.pipelines = {xss_name: MagicMock()}
        mock_eng.config.data.pipelines[xss_name].schedule = None

        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app, follow_redirects=False)

            # Log in.
            resp = client.post("/login", data={"passphrase": _API_KEY})
            assert resp.status_code in (302, 303)

            # Fetch the pipelines page — the XSS name should be HTML-escaped.
            resp = client.get("/data/pipelines")
            assert resp.status_code == 200
            # Jinja2 auto-escapes in HTML body context.
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text, (
                "XSS payload was not escaped by the template engine in HTML body"
            )

    def test_xss_source_name_escaped_in_catalog(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hash_file = tmp_path / "auth.hash"
        hash_file.write_text(_hash_password(_API_KEY))
        monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
            # Fetch the pipelines page — the XSS name should not appear raw.
            resp = client.get("/data/pipelines")
            assert resp.status_code == 200
            # Jinja2 auto-escapes in HTML body context.
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resp.text, (
                "XSS payload was not escaped by the template engine in HTML body"
            )

    def test_xss_source_name_escaped_in_catalog(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hash_file = tmp_path / "auth.hash"
        hash_file.write_text(_hash_password(_API_KEY))
        monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)

        xss_name = '<img src=x onerror=alert("xss")>'
        mock_eng = _make_engine_mock()
        mock_eng.config.data.sources = {xss_name: SimpleNamespace(type="csv", path="/tmp/test.csv")}
        mock_eng.config.data.sources = {xss_name: MagicMock()}

        with patch("dex_studio._engine.get_engine", return_value=mock_eng):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app, follow_redirects=False)
            client.post("/login", data={"passphrase": _API_KEY})

            resp = client.get("/data/sources")
            assert resp.status_code == 200
            # Must not contain the raw onerror payload.
            assert 'onerror=alert("xss")' not in resp.text, (
                "XSS payload in source name was not escaped"
            )
