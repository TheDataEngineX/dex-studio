"""Performance tests for DEX Studio routes using TestClient (no real server)."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password

_API_KEY = "test-perf-key-abc"  # gitleaks:allow
_SESSION_SECRET = "p" * 32

_LATENCY_LIMIT_MS = 2000
_SEQUENTIAL_50_LIMIT_S = 10.0
_CONCURRENT_THREADS = 10


def _make_engine_mock() -> MagicMock:
    eng = MagicMock()
    eng.config.project.name = "PerfProject"
    eng.config_path = "/tmp/perf_test.yaml"
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
    eng.store.lineage_summary.return_value = {
        "total_events": 0,
        "by_layer": {},
        "by_operation": {},
    }
    eng.store.get_memory.return_value = []
    eng.ai_memory = None
    eng.ai_long_memory = None
    eng.ai_episodic = None
    eng.ai_audit = None
    eng.ai_metrics = None
    return eng


def _reset_rate_limiter() -> None:
    """Clear the rate-limiter singleton so prior test failures don't block login."""
    import dex_studio.auth as _auth

    with _auth._limiter._lock:
        _auth._limiter._failures.clear()


@pytest.fixture
def perf_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[TestClient]:
    """Authenticated TestClient for each performance test."""
    _reset_rate_limiter()
    hash_file = tmp_path / "auth.hash"
    hash_file.write_text(_hash_password(_API_KEY))
    monkeypatch.setattr("dex_studio.auth._HASH_FILE", hash_file)
    """Authenticated TestClient for each performance test."""
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
        assert resp.status_code in (302, 303), f"Perf test login failed: {resp.status_code}"
        yield client
    _reset_rate_limiter()


# ── Baseline latency ──────────────────────────────────────────────────────────


class TestBaselineLatency:
    """Single requests to key routes must complete within the latency budget."""

    _KEY_ROUTES = [
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
    ]

    @pytest.mark.parametrize("path", _KEY_ROUTES)
    def test_route_latency_under_budget(self, perf_client: TestClient, path: str) -> None:
        start = time.perf_counter()
        resp = perf_client.get(path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Status check: authenticated so must not redirect to login.
        assert resp.status_code in (200, 302, 303), (
            f"{path} returned unexpected status {resp.status_code}"
        )
        assert elapsed_ms < _LATENCY_LIMIT_MS, (
            f"{path} took {elapsed_ms:.1f}ms, budget is {_LATENCY_LIMIT_MS}ms"
        )

    def test_hub_latency_under_budget(self, perf_client: TestClient) -> None:
        start = time.perf_counter()
        resp = perf_client.get("/")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        assert elapsed_ms < _LATENCY_LIMIT_MS, (
            f"Hub took {elapsed_ms:.1f}ms, budget is {_LATENCY_LIMIT_MS}ms"
        )

    def test_login_page_latency_under_budget(self, perf_client: TestClient) -> None:
        """Public login page must also be fast (no engine needed)."""
        start = time.perf_counter()
        resp = perf_client.get("/login")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        assert elapsed_ms < _LATENCY_LIMIT_MS, f"Login page took {elapsed_ms:.1f}ms"
        assert elapsed_ms < _LATENCY_LIMIT_MS, f"Login page took {elapsed_ms:.1f}ms"


# ── Sequential throughput ─────────────────────────────────────────────────────


class TestSequentialThroughput:
    """50 sequential GETs to the hub must complete in under 10 seconds total."""

    def test_50_sequential_hub_requests(self, perf_client: TestClient) -> None:
        n = 50
        start = time.perf_counter()
        for _ in range(n):
            resp = perf_client.get("/")
            assert resp.status_code == 200, "Hub returned non-200 during throughput test"
        elapsed = time.perf_counter() - start

        assert elapsed < _SEQUENTIAL_50_LIMIT_S, (
            f"{n} sequential requests took {elapsed:.2f}s, budget is {_SEQUENTIAL_50_LIMIT_S}s"
            f"{n} sequential requests took {elapsed:.2f}s, "
            f"budget is {_SEQUENTIAL_50_LIMIT_S}s"
        )

    def test_20_sequential_data_pipeline_requests(self, perf_client: TestClient) -> None:
        n = 20
        start = time.perf_counter()
        for _ in range(n):
            resp = perf_client.get("/data/pipelines")
            assert resp.status_code == 200
        elapsed = time.perf_counter() - start

        # 20 requests — proportional budget (10s / 50 * 20 = 4s).
        budget = 4.0
        assert elapsed < budget, (
            f"{n} pipeline page requests took {elapsed:.2f}s, budget is {budget}s"
        )

    def test_login_page_50_sequential(self, perf_client: TestClient) -> None:
        """Login page (public, no engine) must be even faster."""
        n = 50
        start = time.perf_counter()
        for _ in range(n):
            resp = perf_client.get("/login")
            assert resp.status_code == 200
        elapsed = time.perf_counter() - start

        assert elapsed < _SEQUENTIAL_50_LIMIT_S, f"{n} login page requests took {elapsed:.2f}s"
        assert elapsed < _SEQUENTIAL_50_LIMIT_S, f"{n} login page requests took {elapsed:.2f}s"


# ── Concurrent requests ───────────────────────────────────────────────────────


class TestConcurrentRequests:
    """10 concurrent GET / requests: all return 200, no crashes."""

    def test_10_concurrent_hub_requests_all_200(self, perf_client: TestClient) -> None:
        results: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def _fetch() -> None:
            try:
                resp = perf_client.get("/")
                with lock:
                    results.append(resp.status_code)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=_fetch) for _ in range(_CONCURRENT_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Exceptions during concurrent requests: {errors}"
        assert len(results) == _CONCURRENT_THREADS, (
            f"Expected {_CONCURRENT_THREADS} responses, got {len(results)}"
        )
        for status in results:
            assert status == 200, f"Concurrent request returned {status}, expected 200"

    def test_20_concurrent_mixed_route_requests(self, perf_client: TestClient) -> None:
        """Mix of routes under concurrency: no crashes, all 2xx/3xx."""
        routes = ["/", "/data/pipelines", "/data/pipelines/status", "/data/sql"] * 5  # 20 total
        results: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def _fetch(path: str) -> None:
            try:
                resp = perf_client.get(path)
                with lock:
                    results.append(resp.status_code)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=_fetch, args=(p,)) for p in routes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        assert not errors, f"Exceptions in mixed concurrent requests: {errors}"
        assert len(results) == len(routes)
        for status in results:
            assert status in (200, 302, 303), f"Unexpected status {status} in concurrent test"

    def test_concurrent_login_attempts(self, perf_client: TestClient) -> None:
        """10 concurrent login page GETs must all return 200 without crashing."""
        results: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def _fetch() -> None:
            try:
                resp = perf_client.get("/login")
                with lock:
                    results.append(resp.status_code)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=_fetch) for _ in range(_CONCURRENT_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Concurrent login page errors: {errors}"
        assert all(s == 200 for s in results), f"Some login page requests failed: {results}"
        assert all(s == 200 for s in results), f"Some login page requests failed: {results}"


# ── Memory safety ─────────────────────────────────────────────────────────────


class TestMemorySafety:
    """100 sequential requests must all return 200 — verifies no cumulative failure."""

    def test_100_sequential_requests_all_succeed(self, perf_client: TestClient) -> None:
        failed: list[tuple[int, int]] = []
        for i in range(100):
            resp = perf_client.get("/")
            if resp.status_code != 200:
                failed.append((i, resp.status_code))

        assert not failed, (
            f"Requests failed at indices: {failed[:5]} (showing first 5 of {len(failed)})"
            f"Requests failed at indices: {failed[:5]} "
            f"(showing first 5 of {len(failed)})"
        )

    def test_100_sequential_json_endpoint_requests(self, perf_client: TestClient) -> None:
        """JSON endpoint (no HTML template) across 100 requests."""
        failed: list[tuple[int, int]] = []
        for i in range(100):
            resp = perf_client.get("/data/pipelines/runs/all")
            if resp.status_code != 200:
                failed.append((i, resp.status_code))

        assert not failed, f"JSON endpoint requests failed at indices: {failed[:5]}"
        assert not failed, f"JSON endpoint requests failed at indices: {failed[:5]}"
