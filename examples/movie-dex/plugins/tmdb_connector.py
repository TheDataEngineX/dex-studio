"""Async, project-local TMDB connector with shared rate limiting."""

from __future__ import annotations

import asyncio
import math
import time
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from dataenginex.core.interfaces import BaseConnector
from dataenginex.data.connectors import connector_registry
from dataenginex.lakehouse.storage import DeltaStorage

logger = structlog.get_logger()

_DEFAULT_APPEND = "credits,external_ids,images,keywords,reviews,similar,videos,watch/providers"

# Circuit breaker state — ponytail: module-level, not per-instance
_cb_failures = 0
_cb_open_until = 0.0
_CB_THRESHOLD = 3  # consecutive failures to open
_CB_COOLDOWN_S = 60.0  # seconds to stay open
_RATE_LIMIT_LUA = """
local now_parts = redis.call('TIME')
local now_ms = (tonumber(now_parts[1]) * 1000) + math.floor(tonumber(now_parts[2]) / 1000)
local next_ms = tonumber(redis.call('GET', KEYS[1])) or now_ms
local slot_ms = math.max(now_ms, next_ms)
redis.call('SET', KEYS[1], slot_ms + tonumber(ARGV[1]), 'PX', tonumber(ARGV[2]))
return slot_ms - now_ms
"""


def _run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine from synchronous connector APIs, including from an active loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[T] = []
    errors: list[BaseException] = []

    def _runner() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result[0]


@connector_registry.decorator("tmdb")
class TmdbConnector(BaseConnector):
    """Fetch one TMDB detail bundle per ID with bounded async concurrency.

    When ``redis_url`` is configured, all replicas coordinate through one
    Redis-backed rate slot. Redis failure degrades to a process-local limiter.
    """

    def __init__(
        self,
        api_key: str,
        id_source_path: str,
        id_column: str = "id",
        media_type: str = "movie",
        append_to_response: str = _DEFAULT_APPEND,
        base_url: str = "https://api.themoviedb.org/3",
        max_concurrency: int = 10,
        requests_per_second: float = 40.0,
        timeout: float = 30.0,
        redis_url: str = "",
        redis_password: str = "",
        redis_rate_key: str = "dex:tmdb:rate-slot",
        **kwargs: Any,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if media_type not in {"movie", "tv"}:
            raise ValueError("media_type must be 'movie' or 'tv'")

        self._api_key = api_key
        self._id_source_path = Path(id_source_path)
        self._id_column = id_column
        self._media_type = media_type
        self._append = append_to_response
        self._base_url = base_url.rstrip("/")
        self._max_concurrency = max_concurrency
        self._rps = requests_per_second
        self._timeout = timeout
        self._redis_url = (redis_url or "").strip()
        self._redis_password = redis_password
        self._redis_rate_key = redis_rate_key
        self._connected = False
        self._redis: Any = None
        self._local_rate_lock: asyncio.Lock | None = None
        self._next_allowed_at = 0.0

    def connect(self) -> None:
        if not self._api_key:
            msg = (
                "TmdbConnector: no api_key configured (TMDB_API_KEY is unset/empty). "
                "Every request would be rejected one-by-one, silently yielding 0 rows — "
                "failing here instead so the pipeline surfaces the real cause. "
                "Set TMDB_API_KEY to a valid key from themoviedb.org."
            )
            raise RuntimeError(msg)
        # httpx.AsyncClient is intentionally NOT created here: this method is
        # sync and runs outside any event loop, but each read()/fetch_one()
        # call gets its own asyncio.run() (see _run_sync). A client's
        # internal connection pool binds to whichever loop is running on its
        # first request — reusing one client across separate asyncio.run()
        # calls means the second call fails with "Event loop is closed" as
        # soon as the first loop exits. Each async entrypoint below opens
        # its own client, scoped to its own asyncio.run() call instead.
        self._connected = True
        if self._redis_url:
            try:
                from redis import asyncio as redis_async

                self._redis = redis_async.from_url(
                    self._redis_url,
                    password=self._redis_password or None,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("tmdb redis limiter unavailable", error=str(exc))
                self._redis = None

    def disconnect(self) -> None:
        """Close Redis connection if it was created."""
        # Don't try to close Redis in a sync context - it requires an event loop
        # that may already be closed. The connection will be cleaned up when
        # the process exits. This avoids "Event loop is closed" errors.
        if self._redis is not None:
            logger.debug("Skipping Redis close in sync context to avoid event loop issues")
        self._redis = None
        self._connected = False

    def _load_ids(self) -> list[int]:
        if not self._id_source_path.exists():
            msg = f"TmdbConnector id_source_path not found: {self._id_source_path}"
            raise RuntimeError(msg)
        if self._id_source_path.is_dir() and (self._id_source_path / "_delta_log").exists():
            records = DeltaStorage(base_path=str(self._id_source_path.parent)).read(
                self._id_source_path.name
            )
            table = pa.Table.from_pylist(records or []).select([self._id_column])
        else:
            table = pq.read_table(str(self._id_source_path), columns=[self._id_column])
        return list(dict.fromkeys(int(v) for v in table.column(self._id_column).to_pylist()))

    async def _wait_for_local_rate_slot(self) -> None:
        if self._local_rate_lock is None:
            self._local_rate_lock = asyncio.Lock()
        async with self._local_rate_lock:
            now = asyncio.get_running_loop().time()
            wait = self._next_allowed_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = asyncio.get_running_loop().time()
            self._next_allowed_at = now + (1.0 / self._rps)

    async def _wait_for_rate_slot(self) -> None:
        if self._redis is not None:
            interval_ms = max(1, math.ceil(1000.0 / self._rps))
            try:
                wait_ms = await self._redis.eval(
                    _RATE_LIMIT_LUA,
                    1,
                    self._redis_rate_key,
                    interval_ms,
                    max(60_000, interval_ms * 100),
                )
                if int(wait_ms) > 0:
                    await asyncio.sleep(int(wait_ms) / 1000.0)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("tmdb redis limiter failed; using local limiter", error=str(exc))
        await self._wait_for_local_rate_slot()

    async def _fetch_one(self, client: httpx.AsyncClient, tmdb_id: int) -> dict[str, Any] | None:
        global _cb_failures, _cb_open_until

        # Circuit breaker — skip requests if open
        if time.monotonic() < _cb_open_until:
            return None

        url = f"{self._base_url}/{self._media_type}/{tmdb_id}"
        params = {"api_key": self._api_key, "append_to_response": self._append}

        for attempt in range(3):
            await self._wait_for_rate_slot()
            try:
                resp = await client.get(url, params=params)
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    logger.error("tmdb request failed — skipped", id=tmdb_id, error=str(exc))
                    _cb_failures += 1
                    if _cb_failures >= _CB_THRESHOLD:
                        _cb_open_until = time.monotonic() + _CB_COOLDOWN_S
                        logger.warning("tmdb circuit breaker opened", failures=_cb_failures)
                    return None
                await asyncio.sleep(2**attempt)
                continue
            if resp.status_code == 404:
                logger.warning("tmdb title not found — skipped", id=tmdb_id)
                return None
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2**attempt))
                await asyncio.sleep(max(0.0, retry_after))
                continue
            try:
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                logger.error("tmdb error response — skipped", id=tmdb_id, error=str(exc))
                _cb_failures += 1
                if _cb_failures >= _CB_THRESHOLD:
                    _cb_open_until = time.monotonic() + _CB_COOLDOWN_S
                    logger.warning("tmdb circuit breaker opened", failures=_cb_failures)
                return None
            # Success — reset circuit breaker
            _cb_failures = 0
            return dict(resp.json())

        logger.error("tmdb retries exhausted — skipped", id=tmdb_id)
        return None

    async def _read_async(self) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(self._max_concurrency)
        batch_size = 500  # ponytail: process in batches to avoid OOM on 10M+ IDs

        async with httpx.AsyncClient(timeout=self._timeout) as client:

            async def _bounded(tmdb_id: int) -> dict[str, Any] | None:
                async with semaphore:
                    return await self._fetch_one(client, tmdb_id)

            all_ids = self._load_ids()
            records: list[dict[str, Any]] = []
            for i in range(0, len(all_ids), batch_size):
                batch = all_ids[i : i + batch_size]
                results = await asyncio.gather(*(_bounded(tid) for tid in batch))
                records.extend(r for r in results if r is not None)
                logger.info("tmdb batch done", batch_start=i, fetched=len(records))
        return records

    async def _fetch_one_standalone(self, tmdb_id: int) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._fetch_one(client, tmdb_id)

    def fetch_one(self, tmdb_id: int) -> dict[str, Any] | None:
        return _run_sync(self._fetch_one_standalone(tmdb_id))

    def read(self, *, table: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        if not self._connected:
            raise RuntimeError("TmdbConnector not connected — call connect() first")
        records = _run_sync(self._read_async())
        logger.info("tmdb connector fan-out complete", fetched=len(records))
        return records

    def write(self, data: Any, *, table: str = "", **kwargs: Any) -> None:
        raise NotImplementedError("TmdbConnector is read-only")

    def health_check(self) -> bool:
        try:
            resp = httpx.get(
                f"{self._base_url}/configuration",
                params={"api_key": self._api_key},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False
