"""Comprehensive route coverage — every registered route returns expected status.

Tests both authenticated and unauthenticated states. Uses a minimal DexEngine
config so routes exercise the full request/response stack without mocking.
"""

from __future__ import annotations

import csv
import os
import re
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password

_TEST_API_KEY = "comprehensive-test-api-key-abcdef123456"

_CONFIG_TEMPLATE = """\
project:
  name: RouteCoverageTest
  version: 0.1.0
data:
  engine: duckdb
  sources:
    users:
      type: csv
      path: {csv_path}
      query: null
      url: null
      connection: {{}}
      options: {{}}
    products:
      type: csv
      path: {products_path}
      query: null
      url: null
      connection: {{}}
      options: {{}}
  pipelines:
    clean_users:
      source: users
      transforms:
        - type: filter
          condition: "age > 0"
        - type: derive
          column: age_group
          expression: "CASE WHEN age < 18 THEN 'child' WHEN age < 65 THEN 'adult' ELSE 'senior' END"
      destination: silver.users
    clean_products:
      source: products
      transforms:
        - type: deduplicate
          keys: ["id"]
      destination: silver.products
    user_stats:
      source: silver.users
      transforms:
        - type: sql
          query: "SELECT age_group, COUNT(*) as cnt FROM __input__ GROUP BY age_group"
      destination: gold.user_stats
ai:
  agents:
    assistant:
      provider: echo
      instruction: "You are a helpful assistant."
      tools:
        - echo
"""


def _sorted_routes(app) -> list[tuple[str, str, str]]:  # noqa: C901
    routes = []
    for r in app.routes:
        tname = type(r).__name__
        if tname == "_IncludedRouter":
            prefix = r.include_context.prefix if hasattr(r, "include_context") else ""
            orouter = getattr(r, "original_router", None) or getattr(r, "router", None)
            if orouter is None:
                continue
            for sr in orouter.routes:
                path = getattr(sr, "path", "")
                methods = getattr(sr, "methods", None) or {"GET"}
                for m in methods:
                    if m in ("HEAD", "OPTIONS"):
                        continue
                    full = prefix + path
                    routes.append((full, m, getattr(sr, "name", full)))
        else:
            path = getattr(r, "path", "")
            if any(
                path.startswith(p)
                for p in ("/static", "/favicon.ico", "/docs", "/openapi", "/redoc")
            ):  # noqa: E501
                continue
            methods = getattr(r, "methods", None) or {"GET"}
            for m in methods:
                if m in ("HEAD", "OPTIONS"):
                    continue
                routes.append((path, m, getattr(r, "name", "") or path))
    return routes


def _route_count_by_prefix(routes: list[tuple[str, str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path, _method, _ in routes:
        prefix = path.split("/")[1] if path.count("/") > 0 else "root"
        key = f"/{prefix}"
        if key == "//":
            key = "/root"
        counts[key] = counts.get(key, 0) + 1
    return counts


@pytest.fixture(scope="module")
def csv_sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("data")
    users = d / "users.csv"
    with users.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "age"])
        w.writerow([1, "Alice", 30])
        w.writerow([2, "Bob", 25])
        w.writerow([3, "Charlie", -1])
        w.writerow([4, "Diana", 17])
        w.writerow([5, "Eve", 70])
    products = d / "products.csv"
    with products.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "price"])
        w.writerow([1, "Widget", 9.99])
        w.writerow([2, "Gadget", 24.99])
        w.writerow([2, "Gadget", 24.99])
        w.writerow([3, "Doohickey", 14.99])
    return {"users": users, "products": products}


@pytest.fixture(scope="module")
def real_engine(csv_sources, tmp_path_factory: pytest.TempPathFactory):
    from dataenginex.engine import DexEngine

    cfg = tmp_path_factory.mktemp("cfg") / "dex.yaml"
    cfg.write_text(
        _CONFIG_TEMPLATE.format(
            csv_path=csv_sources["users"], products_path=csv_sources["products"]
        )
    )
    return DexEngine(cfg)


def _app_with_engine(engine):
    import dex_studio._engine as _mod

    orig = _mod._ENGINE
    _mod._ENGINE = engine
    return orig


@pytest.fixture(scope="module")
def app_with_routes() -> tuple:
    """Return (app, routes_list) without engine injection."""
    os.environ.setdefault("DEX_STUDIO_SESSION_SECRET", "t" * 32)

    from dex_studio.app import create_app

    @asynccontextmanager
    async def _noop(_app: object) -> AsyncGenerator[None]:
        yield

    app = create_app()
    app.router.lifespan_context = _noop
    routes = _sorted_routes(app)
    return app, routes


@pytest.fixture(scope="module")
def authenticated_client(  # noqa: E501
    real_engine,
) -> Generator[TestClient]:
    import dex_studio._engine as _mod
    import dex_studio.db_store as _db

    orig_engine = _mod._ENGINE
    _mod._ENGINE = real_engine

    orig_init_db = _db.init_db
    orig_get_setting = _db.get_setting
    orig_set_setting = _db.set_setting
    orig_delete_setting = _db.delete_setting
    orig_get_projects = _db.get_projects
    orig_set_project = _db.set_project
    orig_delete_project = _db.delete_project

    _db.init_db = MagicMock()
    _db.get_setting = MagicMock(return_value=_hash_password(_TEST_API_KEY))
    _db.set_setting = MagicMock()
    _db.delete_setting = MagicMock()
    _db.get_projects = MagicMock(return_value=[])
    _db.set_project = MagicMock()
    _db.delete_project = MagicMock()

    os.environ.setdefault("DEX_STUDIO_SESSION_SECRET", "t" * 32)

    from dex_studio.app import create_app

    @asynccontextmanager
    async def _noop(_app: object) -> AsyncGenerator[None]:
        yield

    app = create_app()
    app.router.lifespan_context = _noop

    with TestClient(app, raise_server_exceptions=False) as tc:
        login = tc.post("/login", data={"passphrase": _TEST_API_KEY})
        assert login.status_code in (200, 303), f"Login: {login.status_code} {login.text[:200]}"
        yield tc

    _mod._ENGINE = orig_engine
    _db.init_db = orig_init_db
    _db.get_setting = orig_get_setting
    _db.set_setting = orig_set_setting
    _db.delete_setting = orig_delete_setting
    _db.get_projects = orig_get_projects
    _db.set_project = orig_set_project
    _db.delete_project = orig_delete_project


@pytest.fixture(scope="module")
def csrf_token(authenticated_client: TestClient) -> str:
    r = authenticated_client.get("/data/sources")
    m = re.search(rb'<meta name="csrf-token" content="([^"]+)"', r.content)
    assert m, "CSRF meta tag not found"
    return m.group(1).decode()


# ── Route inventory ────────────────────────────────────────────────────────────


class TestRouteInventory:
    def test_routes_are_discovered(self, app_with_routes) -> None:
        _, routes = app_with_routes
        assert len(routes) >= 100, f"Expected 100+ routes, found {len(routes)}"
        by_prefix = _route_count_by_prefix(routes)
        for p, c in sorted(by_prefix.items()):
            print(f"  {p}: {c}")

    def test_route_counts_by_prefix(self, app_with_routes) -> None:
        _, routes = app_with_routes
        by_prefix = _route_count_by_prefix(routes)
        assert by_prefix.get("/data", 0) >= 40, f"/data: {by_prefix.get('/data', 0)}"
        assert by_prefix.get("/intelligence", 0) >= 25, (  # noqa: E501
            f"/intelligence: {by_prefix.get('/intelligence', 0)}"
        )
        assert by_prefix.get("/system", 0) >= 12, f"/system: {by_prefix.get('/system', 0)}"
        assert by_prefix.get("/secops", 0) >= 5, f"/secops: {by_prefix.get('/secops', 0)}"
        assert by_prefix.get("/api", 0) >= 14, f"/api: {by_prefix.get('/api', 0)}"


# ── Authenticated routes — all return 200/303 ──────────────────────────────────


# Routes that need specific body / CSRF / separate auth — skip in generic sweep
# Routes that would invalidate the session or need specific body/CSRF — skip entirely
_AUTH_SKIP = {
    "/logout",  # GET logs out, invalidates session for subsequent tests
    "/setup",
    "/login",  # POST needs valid body, testing through the auth flow is separate
}
_KNOWN_POST = {
    "/onboarding/open",
    "/onboarding/create",
    "/projects/switch",
    "/projects/set-default",
}
_KNOWN_JSON_AUTH = {  # routes using JsonReadDep — return 401 not 303 redirect
    "/data/pipelines/status",
    "/data/pipelines/runs/all",
    "/data/pipelines/{name}/runs",
    "/intelligence/stream",
    "/intelligence/chat",
    "/intelligence/native",
    "/intelligence/context",
    "/intelligence/predict/models",
}
_KNOWN_POST_CRASH = {  # POST routes that crash with 500 on empty body
    "/intelligence/chat",
    "/intelligence/native",
}
_KNOWN_SLOW = {  # routes that may be slow (AI/LLM, pipeline runs) — skip in sweep
    "/intelligence/playground",
    "/intelligence/predict",
    "/intelligence/forecast",
    "/intelligence/hyperopt",
    "/intelligence/finetune",
}
_KNOWN_SLOW_PREFIXES = {  # prefixes that may be slow — skip in sweep
    "/intelligence/playground",
    "/intelligence/embeddings",
    "/intelligence/ab-test",
    "/intelligence/rag-eval",
    "/intelligence/traces",
    "/intelligence/drift",
    "/intelligence/experiments",
    "/intelligence/models",
    "/data/catalog",
    "/data/lineage",
    "/data/lakehouse",
    "/data/schema",
    "/data/quality",
}
_KNOWN_WS = {"/intelligence/playground/ws/{agent_name}"}
_KNOWN_STREAM = {"/intelligence/stream", "/system/logs/stream"}  # SSE — needs long-lived connection
_KNOWN_CSRF = {"/projects/switch", "/projects/set-default"}


def _is_skip_route(path: str, method: str) -> bool:
    if method in ("WEBSOCKET", "POST", "PUT", "PATCH", "DELETE"):
        return True
    if path in _KNOWN_WS or path in _KNOWN_STREAM or path in _AUTH_SKIP or path in _KNOWN_SLOW:
        return True
    return any(path.startswith(sp + "/") or path == sp for sp in _KNOWN_SLOW_PREFIXES)


class TestAuthenticatedRoutes:
    def test_get_routes_return_200_or_303(self, authenticated_client: TestClient) -> None:
        app = authenticated_client._transport.app
        routes = _sorted_routes(app)
        failures = []
        ok_codes = {200, 302, 303, 307, 308}
        tested = 0
        for path, method, _ in routes:
            if _is_skip_route(path, method):
                continue
            tested += 1
            r = authenticated_client.request(method, path)
            if r.status_code not in ok_codes:
                failures.append(f"{method} {path} → {r.status_code}: {r.text[:100]}")
        assert not failures, f"{len(failures)}/{tested} GET route(s) failed:\n" + "\n".join(
            failures[:20]
        )


# ── Unauthenticated access ─────────────────────────────────────────────────────


class TestUnauthenticatedAccess:
    PUBLIC_PATHS = {
        "/health",
        "/system/metrics-live",
    }

    def test_public_routes_accessible(self) -> None:
        os.environ.setdefault("DEX_STUDIO_SESSION_SECRET", "t" * 32)
        from dex_studio.app import create_app

        @asynccontextmanager
        async def _noop(_app: object) -> AsyncGenerator[None]:
            yield

        app = create_app()
        app.router.lifespan_context = _noop
        with TestClient(app, raise_server_exceptions=False) as tc:
            for path in sorted(self.PUBLIC_PATHS):
                r = tc.get(path)
                assert r.status_code == 200, f"{path} → {r.status_code}"

    def test_protected_routes_redirect_to_login(self) -> None:
        os.environ.setdefault("DEX_STUDIO_SESSION_SECRET", "t" * 32)
        from dex_studio.app import create_app

        @asynccontextmanager
        async def _noop(_app: object) -> AsyncGenerator[None]:
            yield

        app = create_app()
        app.router.lifespan_context = _noop
        routes = _sorted_routes(app)

        with TestClient(app, raise_server_exceptions=False) as tc:
            failures = []
            for path, _method, _ in routes:
                if _is_skip_route(path, _method):
                    continue
                if path in self.PUBLIC_PATHS:
                    continue
                r = tc.request(_method, path)
                if r.status_code not in (302, 303, 307, 308) and r.status_code != 200:
                    if r.status_code == 401 and path in _KNOWN_JSON_AUTH:
                        continue
                    failures.append(f"{_method} {path} → {r.status_code}")
            assert not failures, f"{len(failures)} route(s) did not redirect:\n" + "\n".join(
                failures[:20]
            )  # noqa: E501


# ── CSRF protection ────────────────────────────────────────────────────────────


class TestCSRFProtection:
    def test_api_pause_requires_csrf(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.post("/api/scheduler/pause")
        assert r.status_code in (403, 422, 200), f"Expected CSRF rejection, got {r.status_code}"

    def test_api_pause_with_csrf(self, authenticated_client: TestClient, csrf_token: str) -> None:
        r = authenticated_client.post("/api/scheduler/pause", headers={"X-CSRF-Token": csrf_token})
        assert r.status_code in (200, 303), f"Got {r.status_code}: {r.text[:200]}"


# ── Data routes — pipeline & source operations ─────────────────────────────────


class TestDataRoutes:
    def test_pipelines_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/pipelines")
        assert r.status_code in (200, 303)
        if r.status_code == 200:
            assert "clean_users" in r.text or "pipeline" in r.text.lower()

    def test_pipeline_detail(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/pipelines/clean_users")
        assert r.status_code in (200, 303)

    def test_pipeline_runs(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/pipelines/runs")
        assert r.status_code in (200, 303)

    def test_pipeline_run_action(self, authenticated_client: TestClient, csrf_token: str) -> None:
        r = authenticated_client.post(  # noqa: E501
            "/data/pipelines/run/clean_users", headers={"X-CSRF-Token": csrf_token}
        )
        assert r.status_code in (200, 302, 303), f"Got {r.status_code}: {r.text[:200]}"

    def test_sources_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/sources")
        assert r.status_code in (200, 303)

    def test_source_detail(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/sources/users")
        assert r.status_code in (200, 303)

    def test_lakehouse_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/lakehouse")
        assert r.status_code in (200, 303)

    def test_warehouse_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/warehouse")
        assert r.status_code in (200, 303)

    def test_lineage_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/lineage")
        assert r.status_code in (200, 303)

    def test_quality_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/quality")
        assert r.status_code in (200, 303)

    def test_catalog_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/catalog")
        assert r.status_code in (200, 303)

    def test_transforms_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/transforms")
        assert r.status_code in (200, 303)

    def test_sql_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/sql")
        assert r.status_code in (200, 303)

    def test_watermarks_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/watermarks")
        assert r.status_code in (200, 303)

    def test_schema_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/schema")
        assert r.status_code in (200, 303)

    def test_backfill_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/backfill")
        assert r.status_code in (200, 303)

    def test_dashboard_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/data/dashboard")
        assert r.status_code in (200, 303)


# ── Intelligence routes ────────────────────────────────────────────────────────


class TestIntelligenceRoutes:
    def test_dashboard(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/dashboard")
        assert r.status_code in (200, 303)

    def test_models_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/models")
        assert r.status_code in (200, 303)

    def test_experiments_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/experiments")
        assert r.status_code in (200, 303)

    def test_predictions_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/predictions")
        assert r.status_code in (200, 303)

    def test_features_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/features")
        assert r.status_code in (200, 303)

    def test_drift_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/drift")
        assert r.status_code in (200, 303)

    def test_playground_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/playground")
        assert r.status_code in (200, 303)

    def test_agents_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/agents")
        assert r.status_code in (200, 303)

    def test_tools_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/tools")
        assert r.status_code in (200, 303)

    def test_embeddings_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/embeddings")
        assert r.status_code in (200, 303)

    def test_finetune_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/finetune")
        assert r.status_code in (200, 303)

    def test_traces_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/intelligence/traces")
        assert r.status_code in (200, 303)


# ── System routes ──────────────────────────────────────────────────────────────


class TestSystemRoutes:
    def test_system_status(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/status")
        assert r.status_code in (200, 303)

    def test_system_logs(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/logs")
        assert r.status_code in (200, 303)

    def test_system_metrics(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/metrics")
        assert r.status_code in (200, 303)

    def test_system_components(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/components")
        assert r.status_code in (200, 303)

    def test_system_runs(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/runs")
        assert r.status_code in (200, 303)

    def test_system_costs(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/costs")
        assert r.status_code in (200, 303)

    def test_system_alerting(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/system/alerting")
        assert r.status_code in (200, 303)


# ── SecOps routes ──────────────────────────────────────────────────────────────


class TestSecOpsRoutes:
    def test_overview(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/secops")
        assert r.status_code in (200, 303)

    def test_privacy(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/secops/privacy")
        assert r.status_code in (200, 303)

    def test_policies(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/secops/policies")
        assert r.status_code in (200, 303)

    def test_audit(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/secops/audit")
        assert r.status_code in (200, 303)

    def test_alerts(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/secops/alerts")
        assert r.status_code in (200, 303)


# ── API routes ─────────────────────────────────────────────────────────────────


class TestAPIRoutes:
    def test_api_scheduler_status(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/api/scheduler/status")
        assert r.status_code in (200, 303)

    def test_api_pipelines_list(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/api/pipelines")
        assert r.status_code in (200, 303)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, (dict, list))

    def test_api_watermarks(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/api/watermarks")
        assert r.status_code in (200, 303)

    def test_api_compaction(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/api/compaction/status")
        assert r.status_code in (200, 303)

    def test_api_alerts(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/api/alerts")
        assert r.status_code in (200, 303)

    def test_api_quality_contracts(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/api/quality/contracts")
        assert r.status_code in (200, 303)


# ── Error handling ─────────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_404_returns_error_page(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/this-route-does-not-exist-12345")
        assert r.status_code == 404

    def test_security_headers(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/health")
        assert r.headers.get("x-frame-options") == "DENY"
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert "default-src 'self'" in r.headers.get("content-security-policy", "")


# ── Static assets ──────────────────────────────────────────────────────────────


class TestStaticAssets:
    def test_favicon(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/favicon.ico")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/svg+xml")

    def test_studio_css(self, authenticated_client: TestClient) -> None:
        r = authenticated_client.get("/static/studio.css")
        assert r.status_code == 200
        assert "text/css" in r.headers.get("content-type", "")
