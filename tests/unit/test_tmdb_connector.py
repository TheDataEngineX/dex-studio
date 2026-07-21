"""Tests for the project-local TmdbConnector (moviedex plugin).

Loaded directly from its file path (not a normal package import) — this
mirrors exactly how dataenginex.core.project_plugins.load_project_plugins
loads it in production, so the test exercises the real loading path.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import tracemalloc
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

_CONNECTOR_PATH = (
    Path(__file__).parents[2] / "examples" / "movie-dex" / "plugins" / "tmdb_connector.py"
)


def _load_tmdb_connector_module() -> Any:
    spec = importlib.util.spec_from_file_location("_test_tmdb_connector", _CONNECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_tmdb_module = _load_tmdb_connector_module()
TmdbConnector = _tmdb_module.TmdbConnector


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body or {}
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            msg = f"HTTP {self.status_code}"
            raise RuntimeError(msg)


class FakeClient:
    def __init__(self, responses: dict[int, list[FakeResponse]]) -> None:
        self._responses = responses
        self.calls: list[int] = []

    async def get(self, url: str, params: dict[str, Any]) -> FakeResponse:
        tmdb_id = int(url.rstrip("/").split("/")[-1])
        self.calls.append(tmdb_id)
        queue = self._responses[tmdb_id]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def aclose(self) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


def _use_fake_client(connector: Any, fake_client: FakeClient) -> None:
    """Wire *fake_client* into *connector* for the new per-call scoped-client
    architecture: connector.connect() is bypassed (no real API key check
    matters here), and the module's httpx.AsyncClient constructor is
    replaced so ``async with httpx.AsyncClient(...) as client`` yields
    *fake_client* instead of a real client."""
    connector._connected = True
    _tmdb_module.httpx.AsyncClient = lambda **_kw: fake_client


@pytest.fixture
def id_parquet(tmp_path: Path) -> Path:
    path = tmp_path / "ids.parquet"
    table = pa.table({"id": [1, 2, 3]})
    pq.write_table(table, str(path))
    return path


def test_fetches_one_bundled_request_per_id(id_parquet: Path) -> None:
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(id_parquet),
        max_concurrency=2,
        requests_per_second=1000.0,
    )
    fake_client = FakeClient(
        {
            1: [FakeResponse(200, {"id": 1, "title": "Movie One"})],
            2: [FakeResponse(200, {"id": 2, "title": "Movie Two"})],
            3: [FakeResponse(200, {"id": 3, "title": "Movie Three"})],
        }
    )
    _use_fake_client(connector, fake_client)

    records = connector.read()

    assert len(records) == 3
    assert sorted(r["id"] for r in records) == [1, 2, 3]
    assert sorted(fake_client.calls) == [1, 2, 3]


def test_skips_404_without_raising(id_parquet: Path) -> None:
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(id_parquet),
        requests_per_second=1000.0,
    )
    fake_client = FakeClient(
        {
            1: [FakeResponse(200, {"id": 1})],
            2: [FakeResponse(404)],
            3: [FakeResponse(200, {"id": 3})],
        }
    )
    _use_fake_client(connector, fake_client)

    records = connector.read()

    assert sorted(r["id"] for r in records) == [1, 3]


def test_retries_on_429_then_succeeds(id_parquet: Path) -> None:
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(id_parquet),
        requests_per_second=1000.0,
    )
    fake_client = FakeClient(
        {
            1: [FakeResponse(429, headers={"Retry-After": "0"}), FakeResponse(200, {"id": 1})],
            2: [FakeResponse(200, {"id": 2})],
            3: [FakeResponse(200, {"id": 3})],
        }
    )
    _use_fake_client(connector, fake_client)

    records = connector.read()

    assert sorted(r["id"] for r in records) == [1, 2, 3]


def test_requests_bundle_append_to_response(id_parquet: Path) -> None:
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(id_parquet),
        requests_per_second=1000.0,
    )
    seen_params: list[dict[str, Any]] = []

    class RecordingClient(FakeClient):
        async def get(self, url: str, params: dict[str, Any]) -> FakeResponse:
            seen_params.append(params)
            return await super().get(url, params)

    fake_client = RecordingClient(
        {
            1: [FakeResponse(200, {"id": 1})],
            2: [FakeResponse(200, {"id": 2})],
            3: [FakeResponse(200, {"id": 3})],
        }
    )
    _use_fake_client(connector, fake_client)

    connector.read()

    assert all("append_to_response" in p for p in seen_params)
    assert seen_params[0]["append_to_response"] == (
        "credits,external_ids,images,keywords,reviews,similar,videos,watch/providers"
    )


def test_respects_max_concurrency(id_parquet: Path) -> None:
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(id_parquet),
        max_concurrency=2,
        requests_per_second=1000.0,
    )

    lock = threading.Lock()
    in_flight = 0
    peak_in_flight = 0

    class ThrottledClient(FakeClient):
        async def get(self, url: str, params: dict[str, Any]) -> FakeResponse:
            nonlocal in_flight, peak_in_flight
            with lock:
                in_flight += 1
                peak_in_flight = max(peak_in_flight, in_flight)
            await asyncio.sleep(0.05)
            try:
                return await super().get(url, params)
            finally:
                with lock:
                    in_flight -= 1

    fake_client = ThrottledClient(
        {
            1: [FakeResponse(200, {"id": 1})],
            2: [FakeResponse(200, {"id": 2})],
            3: [FakeResponse(200, {"id": 3})],
        }
    )
    _use_fake_client(connector, fake_client)

    connector.read()

    assert peak_in_flight <= 2


def test_missing_id_source_path_raises(tmp_path: Path) -> None:
    connector = TmdbConnector(api_key="key", id_source_path=str(tmp_path / "missing.parquet"))
    connector._connected = True

    with pytest.raises(RuntimeError, match="id_source_path not found"):
        connector.read()


def test_redis_limiter_coordinates_every_request(id_parquet: Path) -> None:
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(id_parquet),
        requests_per_second=1000.0,
    )
    _use_fake_client(
        connector,
        FakeClient({movie_id: [FakeResponse(200, {"id": movie_id})] for movie_id in (1, 2, 3)}),
    )

    class FakeRedis:
        def __init__(self) -> None:
            self.calls = 0

        async def eval(self, *args: Any) -> int:
            self.calls += 1
            return 0

    redis = FakeRedis()
    connector._redis = redis

    connector.read()

    assert redis.calls == 3


def test_large_fanout_keeps_memory_bounded(tmp_path: Path) -> None:
    ids = list(range(200))
    path = tmp_path / "many-ids.parquet"
    pq.write_table(pa.table({"id": ids}), path)
    connector = TmdbConnector(
        api_key="key",
        id_source_path=str(path),
        max_concurrency=5,
        requests_per_second=100_000.0,
    )
    _use_fake_client(
        connector,
        FakeClient(
            {movie_id: [FakeResponse(200, {"id": movie_id, "title": "x"})] for movie_id in ids}
        ),
    )

    tracemalloc.start()
    records = connector.read()
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(records) == 200
    assert peak < 10 * 1024 * 1024
