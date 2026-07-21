"""Idempotent RabbitMQ handler for on-demand MovieDEX enrichment."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import structlog
from dataenginex.lakehouse.storage import DeltaStorage
from dataenginex.orm import JobState, create_all, get_engine, get_session

logger = structlog.get_logger()


class _TitleFetcher(Protocol):
    def fetch_one(self, tmdb_id: int) -> dict[str, Any] | None: ...


class MovieEnrichmentHandler:
    """Fetch a movie once, persist the event to Delta, and track durable job state."""

    def __init__(
        self,
        connector: _TitleFetcher,
        output_path: str | Path,
        db_url: str,
    ) -> None:
        self._connector = connector
        self._output_path = Path(output_path)
        self._engine = get_engine(db_url)
        create_all(self._engine)

    def _set_state(
        self,
        *,
        job_id: str,
        payload: dict[str, Any],
        status: str,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with get_session(self._engine) as session:
            state = session.get(JobState, job_id)
            if state is None:
                state = JobState(
                    job_id=job_id,
                    job_type="tmdb_movie_enrichment",
                    status=status,
                    payload=payload,
                    created_at=now,
                    updated_at=now,
                    error_message=error,
                )
                session.add(state)
            else:
                state.status = status
                state.updated_at = now
                state.error_message = error
            session.commit()

    def __call__(self, message: dict[str, Any]) -> bool:
        movie_id = message.get("movie_id")
        if not isinstance(movie_id, int):
            logger.error("enrichment message missing/invalid movie_id", message=message)
            return False
        job_id = str(message.get("job_id") or f"tmdb-movie-{movie_id}")

        with get_session(self._engine) as session:
            existing = session.get(JobState, job_id)
            if existing is not None and existing.status == "done":
                return True

        self._set_state(job_id=job_id, payload=message, status="running")
        try:
            record = self._connector.fetch_one(movie_id)
            if record is None:
                self._set_state(
                    job_id=job_id,
                    payload=message,
                    status="failed",
                    error="TMDB fetch returned no record",
                )
                return False

            record["_dex_job_id"] = job_id
            record["_dex_enriched_at"] = datetime.now(UTC).isoformat()
            storage = DeltaStorage(base_path=str(self._output_path.parent), mode="append")
            if not storage.write([record], self._output_path.name):
                raise RuntimeError("Delta enrichment event write failed")
            self._set_state(job_id=job_id, payload=message, status="done")
            logger.info("movie enriched", movie_id=movie_id, job_id=job_id)
            return True
        except Exception as exc:  # noqa: BLE001
            self._set_state(
                job_id=job_id,
                payload=message,
                status="failed",
                error=str(exc),
            )
            logger.error("movie enrichment failed", movie_id=movie_id, error=str(exc))
            return False
