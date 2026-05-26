"""Job cache — DuckDB-backed deduplication with instant results.

Jobs are stored keyed by URL so the same posting is never shown twice
across searches or sessions. A background fetch refreshes the cache while
the UI shows cached results immediately (< 5 ms from DuckDB).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import structlog

from careerdex.models.job import JobPosting, JobSource

logger = structlog.get_logger()
__all__ = ["JobCacheService"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "jobs_cache.duckdb"
_TTL_HOURS = 24

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs_cache (
    url              VARCHAR PRIMARY KEY,
    id               VARCHAR NOT NULL,
    title            VARCHAR NOT NULL,
    company          VARCHAR NOT NULL,
    location         VARCHAR DEFAULT '',
    remote           BOOLEAN DEFAULT false,
    description      VARCHAR DEFAULT '',
    salary_min       DOUBLE,
    salary_max       DOUBLE,
    salary_currency  VARCHAR DEFAULT 'USD',
    required_skills  VARCHAR DEFAULT '[]',
    experience_level VARCHAR DEFAULT '',
    employment_type  VARCHAR DEFAULT '',
    source           VARCHAR DEFAULT 'manual',
    posted_date      TIMESTAMP,
    fetched_at       TIMESTAMP NOT NULL,
    is_new           BOOLEAN DEFAULT true
);
"""


class JobCacheService:
    """DuckDB-backed job cache with URL-based deduplication.

    Usage::

        with JobCacheService() as cache:
            new_count = cache.store(jobs)         # upsert, dedup by URL
            cached = cache.search("data engineer") # instant DuckDB LIKE
            cache.mark_seen(job.url)              # clears 'new' badge
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(_CREATE_TABLE)
        logger.debug("job_cache_ready", db=str(self._db_path))

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()

    def __enter__(self) -> JobCacheService:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, jobs: list[JobPosting]) -> int:
        """Upsert jobs. Returns count of genuinely new insertions."""
        new_count = 0
        for job in jobs:
            if not job.url:
                continue
            exists = self._conn.execute(
                "SELECT 1 FROM jobs_cache WHERE url = ?", [job.url]
            ).fetchone()
            if exists:
                continue
            self._conn.execute(
                """
                INSERT INTO jobs_cache (
                    url, id, title, company, location, remote, description,
                    salary_min, salary_max, salary_currency, required_skills,
                    experience_level, employment_type, source, posted_date,
                    fetched_at, is_new
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true)
                """,
                [
                    job.url,
                    job.id,
                    job.title,
                    job.company,
                    job.location,
                    job.remote,
                    job.description,
                    job.salary_min,
                    job.salary_max,
                    job.salary_currency,
                    json.dumps(job.required_skills),
                    job.experience_level,
                    job.employment_type,
                    job.source.value,
                    job.posted_date.isoformat() if job.posted_date else None,
                    job.fetched_at.isoformat(),
                ],
            )
            new_count += 1
        if new_count:
            logger.info("jobs_cached", new=new_count, total=self.total())
        return new_count

    def mark_seen(self, url: str) -> None:
        """Clear is_new flag when user views a job."""
        self._conn.execute("UPDATE jobs_cache SET is_new = false WHERE url = ?", [url])

    def mark_all_seen(self) -> None:
        """Clear all is_new flags (e.g. on full results page load)."""
        self._conn.execute("UPDATE jobs_cache SET is_new = false")

    def clear_old(self, max_age_hours: int = _TTL_HOURS * 2) -> int:
        """Delete jobs older than max_age_hours. Returns count removed."""
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        result = self._conn.execute(
            "SELECT COUNT(*) FROM jobs_cache WHERE fetched_at < ?", [cutoff]
        ).fetchone()
        count = int(result[0]) if result else 0
        if count:
            self._conn.execute("DELETE FROM jobs_cache WHERE fetched_at < ?", [cutoff])
            logger.info("cache_evicted", count=count)
        return count

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(
        self,
        keywords: str = "",
        *,
        remote_only: bool = False,
        max_results: int = 100,
        max_age_hours: int = _TTL_HOURS,
        new_first: bool = True,
    ) -> list[JobPosting]:
        """Keyword search from cache. Returns in < 5 ms."""
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        conditions = ["fetched_at >= ?"]
        params: list[object] = [cutoff]

        if keywords:
            kw = f"%{keywords.lower()}%"
            conditions.append(
                "(LOWER(title) LIKE ? OR LOWER(company) LIKE ? OR LOWER(description) LIKE ?)"
            )
            params.extend([kw, kw, kw])

        if remote_only:
            conditions.append("remote = true")

        where = " AND ".join(conditions)
        order = "is_new DESC, fetched_at DESC" if new_first else "fetched_at DESC"
        rows = self._conn.execute(
            f"SELECT * FROM jobs_cache WHERE {where} ORDER BY {order} LIMIT ?",
            [*params, max_results],
        ).fetchall()
        return [self._row_to_posting(r) for r in rows]

    def recent(self, max_age_hours: int = _TTL_HOURS, max_results: int = 100) -> list[JobPosting]:
        """All cached jobs newer than max_age_hours, newest first."""
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM jobs_cache WHERE fetched_at >= ? "
            "ORDER BY is_new DESC, fetched_at DESC LIMIT ?",
            [cutoff, max_results],
        ).fetchall()
        return [self._row_to_posting(r) for r in rows]

    def new_count(self) -> int:
        """Number of unviewed (is_new=true) cached jobs."""
        result = self._conn.execute(
            "SELECT COUNT(*) FROM jobs_cache WHERE is_new = true"
        ).fetchone()
        return int(result[0]) if result else 0

    def total(self) -> int:
        """Total cached jobs."""
        result = self._conn.execute("SELECT COUNT(*) FROM jobs_cache").fetchone()
        return int(result[0]) if result else 0

    def stats(self) -> dict[str, int]:
        """Count by source."""
        rows = self._conn.execute(
            "SELECT source, COUNT(*) FROM jobs_cache GROUP BY source"
        ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _row_to_posting(self, row: tuple[object, ...]) -> JobPosting:
        (
            url,
            id_,
            title,
            company,
            location,
            remote,
            description,
            salary_min,
            salary_max,
            salary_currency,
            required_skills_json,
            experience_level,
            employment_type,
            source,
            posted_date,
            fetched_at,
            _is_new,
        ) = row

        try:
            skills: list[str] = json.loads(str(required_skills_json or "[]"))
        except Exception:
            skills = []

        try:
            src = JobSource(str(source))
        except ValueError:
            src = JobSource.MANUAL

        return JobPosting(
            id=str(id_),
            title=str(title),
            company=str(company),
            location=str(location or ""),
            remote=bool(remote),
            url=str(url or ""),
            description=str(description or ""),
            salary_min=float(str(salary_min)) if salary_min is not None else None,
            salary_max=float(str(salary_max)) if salary_max is not None else None,
            salary_currency=str(salary_currency or "USD"),
            required_skills=skills if isinstance(skills, list) else [],
            experience_level=str(experience_level or ""),
            employment_type=str(employment_type or ""),
            source=src,
            posted_date=(
                datetime.fromisoformat(str(posted_date)).replace(tzinfo=UTC)
                if posted_date
                else None
            ),
            fetched_at=(
                datetime.fromisoformat(str(fetched_at)).replace(tzinfo=UTC)
                if fetched_at
                else datetime.now(UTC)
            ),
        )

    # ------------------------------------------------------------------
    # Vector Embeddings (optional DataEngineX integration)
    # ------------------------------------------------------------------

    def embed_jobs(self, jobs: list[JobPosting] | None = None) -> bool:
        """Embed cached jobs for semantic search. Returns True if successful."""
        try:
            from careerdex.services.job_vector_search import JobVectorSearch

            postings = jobs or self.recent(max_results=500)
            job_dicts = [p.model_dump() for p in postings]
            search = JobVectorSearch()
            search.index_jobs(job_dicts)
            logger.info("jobs_embedded", count=len(job_dicts))
            return True
        except ImportError:
            logger.warning("job_vector_search not available")
            return False
        except Exception as exc:
            logger.error("embed_jobs_failed", error=str(exc))
            return False
