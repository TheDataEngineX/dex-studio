"""TmdbConnector — fans out to TMDB's per-title endpoints for a curated ID set.

Project-local plugin (deliberately NOT part of dataenginex core — see
dataenginex/docs/superpowers/specs/2026-07-06-tmdb-data-intelligence-rearchitecture-design.md
for why this lives in the moviedex project instead).

Reads a list of TMDB IDs from a previously-run pipeline's parquet output,
then fetches each title's full detail bundle in ONE call via TMDB's
append_to_response parameter (credits+images+keywords+reviews+similar+
videos+watch/providers bundled together) instead of 7 separate calls.

Self-registers as connector type "tmdb" via the same
@connector_registry.decorator(...) mechanism every core connector uses —
importing this module (done by dataenginex.core.project_plugins.
load_project_plugins) is what makes "type: tmdb" resolvable in dex.yaml.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pyarrow.parquet as pq
import structlog

from dataenginex.core.interfaces import BaseConnector
from dataenginex.data.connectors import connector_registry

logger = structlog.get_logger()

_DEFAULT_APPEND = "credits,images,keywords,reviews,similar,videos,watch/providers"


@connector_registry.decorator("tmdb")
class TmdbConnector(BaseConnector):
    """Fan out to TMDB's per-title detail endpoint for a curated ID set.

    Args:
        api_key: TMDB v3 API key.
        id_source_path: Path to a parquet file (a prior pipeline's bronze
            output) containing the IDs to enrich.
        id_column: Column in that parquet file holding the TMDB ID.
        media_type: "movie" or "tv" — selects the TMDB endpoint family.
        append_to_response: Comma-separated TMDB sub-resources to bundle
            into a single request per title.
        base_url: TMDB API base URL.
        max_concurrency: Max simultaneous in-flight requests (bounded
            concurrency — protects both TMDB's rate limit and local
            CPU/memory from an unbounded burst).
        requests_per_second: Shared rate-limit budget across all threads.
        timeout: Per-request HTTP timeout in seconds.
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
        **kwargs: Any,
    ) -> None:
        self._api_key = api_key
        self._id_source_path = Path(id_source_path)
        self._id_column = id_column
        self._media_type = media_type
        self._append = append_to_response
        self._base_url = base_url.rstrip("/")
        self._max_concurrency = max_concurrency
        self._rps = requests_per_second
        self._timeout = timeout
        self._client: httpx.Client | None = None
        self._rate_lock = threading.Lock()
        self._next_allowed_at = 0.0

    def connect(self) -> None:
        self._client = httpx.Client(timeout=self._timeout)

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _load_ids(self) -> list[int]:
        if not self._id_source_path.exists():
            msg = f"TmdbConnector id_source_path not found: {self._id_source_path}"
            raise RuntimeError(msg)
        table = pq.read_table(str(self._id_source_path), columns=[self._id_column])
        return [int(v) for v in table.column(self._id_column).to_pylist()]

    def _wait_for_rate_slot(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            wait = self._next_allowed_at - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_allowed_at = now + (1.0 / self._rps)

    def fetch_one(self, tmdb_id: int) -> dict[str, Any] | None:
        """Fetch one title's full detail bundle by TMDB ID.

        Public so callers needing a single on-demand title (e.g. the
        RabbitMQ "enrich movie X" job handler) can reuse this exact
        fetch/retry/rate-limit logic instead of duplicating TMDB API-call
        code. Returns None (never raises) on 404, exhausted retries, or
        a request error — same "skip, don't crash" contract as ``read()``.
        """
        assert self._client is not None
        url = f"{self._base_url}/{self._media_type}/{tmdb_id}"
        params = {"api_key": self._api_key, "append_to_response": self._append}

        for _attempt in range(3):
            self._wait_for_rate_slot()
            try:
                resp = self._client.get(url, params=params)
            except Exception as exc:
                logger.error("tmdb request failed — skipped", id=tmdb_id, error=str(exc))
                return None
            if resp.status_code == 404:
                logger.warning("tmdb title not found — skipped", id=tmdb_id)
                return None
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1.0))
                logger.warning(
                    "tmdb rate limited — backing off", id=tmdb_id, retry_after=retry_after
                )
                time.sleep(retry_after)
                continue
            try:
                resp.raise_for_status()
            except Exception as exc:
                logger.error("tmdb error response — skipped", id=tmdb_id, error=str(exc))
                return None
            return dict(resp.json())

        logger.error("tmdb retries exhausted — skipped", id=tmdb_id)
        return None

    def read(self, *, table: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        if self._client is None:
            msg = "TmdbConnector not connected — call connect() first"
            raise RuntimeError(msg)

        ids = self._load_ids()
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=self._max_concurrency) as pool:
            for record in pool.map(self.fetch_one, ids):
                if record is not None:
                    results.append(record)

        logger.info("tmdb connector fan-out complete", requested=len(ids), fetched=len(results))
        return results

    def write(self, data: Any, *, table: str = "", **kwargs: Any) -> None:
        raise NotImplementedError("TmdbConnector is read-only")

    def health_check(self) -> bool:
        try:
            resp = httpx.get(
                f"{self._base_url}/configuration", params={"api_key": self._api_key}, timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False
