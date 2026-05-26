"""Job store — DuckDB-backed CRUD for job postings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import structlog

from careerdex.models.job import JobPosting, JobSource

logger = structlog.get_logger()

__all__ = ["JobStore"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "jobs.duckdb"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id                      VARCHAR PRIMARY KEY,
    title                   VARCHAR NOT NULL,
    company                 VARCHAR NOT NULL,
    company_id              VARCHAR DEFAULT '',
    location               VARCHAR DEFAULT '',
    remote                 BOOLEAN DEFAULT FALSE,
    url                    VARCHAR DEFAULT '',
    description            VARCHAR DEFAULT '',
    description_embedding_json VARCHAR DEFAULT '[]',
    requirements_json      VARCHAR DEFAULT '[]',
    benefits_json          VARCHAR DEFAULT '[]',
    salary_min            DOUBLE,
    salary_max            DOUBLE,
    salary_currency      VARCHAR DEFAULT 'USD',
    required_skills_json  VARCHAR DEFAULT '[]',
    experience_level     VARCHAR DEFAULT '',
    employment_type      VARCHAR DEFAULT 'full_time',
    source               VARCHAR NOT NULL DEFAULT 'manual',
    posted_date          TIMESTAMP,
    fetched_at          TIMESTAMP NOT NULL,
    last_synced_at       TIMESTAMP NOT NULL,
    is_active            BOOLEAN DEFAULT TRUE,
    metadata_json       VARCHAR DEFAULT '{}'
);
"""


class JobStore:
    """DuckDB-backed job postings store.

    Usage::

        store = JobStore()
        store.upsert(JobPosting(title="SWE", company="Acme"))
        job = store.get(job_id)
        jobs = store.list_all()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(_CREATE_TABLE)
        logger.info("job_store_ready", db=str(self._db_path))

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()

    # -- CRUD -------------------------------------------------------------

    def upsert(self, job: JobPosting) -> JobPosting:
        """Insert or update a job posting."""
        self._conn.execute(
            """
            INSERT INTO jobs (
                id, title, company, company_id, location, remote, url, description,
                description_embedding_json, requirements_json, benefits_json,
                salary_min, salary_max, salary_currency, required_skills_json,
                experience_level, employment_type, source,
                posted_date, fetched_at, last_synced_at, is_active, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                title = excluded.title,
                company = excluded.company,
                company_id = excluded.company_id,
                location = excluded.location,
                remote = excluded.remote,
                url = excluded.url,
                description = excluded.description,
                description_embedding_json = excluded.description_embedding_json,
                requirements_json = excluded.requirements_json,
                benefits_json = excluded.benefits_json,
                salary_min = excluded.salary_min,
                salary_max = excluded.salary_max,
                salary_currency = excluded.salary_currency,
                required_skills_json = excluded.required_skills_json,
                experience_level = excluded.experience_level,
                employment_type = excluded.employment_type,
                source = excluded.source,
                posted_date = excluded.posted_date,
                fetched_at = excluded.fetched_at,
                last_synced_at = excluded.last_synced_at,
                is_active = excluded.is_active,
                metadata_json = excluded.metadata_json
            """,
            [
                job.id,
                job.title,
                job.company,
                job.company_id,
                job.location,
                job.remote,
                job.url,
                job.description,
                json.dumps(job.description_embedding),
                json.dumps(job.requirements),
                json.dumps(job.benefits),
                job.salary_min,
                job.salary_max,
                job.salary_currency,
                json.dumps(job.required_skills),
                job.experience_level,
                job.employment_type,
                job.source.value,
                job.posted_date.isoformat() if job.posted_date else None,
                job.fetched_at.isoformat(),
                job.last_synced_at.isoformat(),
                job.is_active,
                json.dumps(job.metadata),
            ],
        )
        logger.info("job_upserted", id=job.id, company=job.company)
        return job

    def get(self, job_id: str) -> JobPosting | None:
        """Fetch a single job posting by ID."""
        result = self._conn.execute("SELECT * FROM jobs WHERE id = ?", [job_id]).fetchone()
        if result is None:
            return None
        return self._row_to_job(result)

    def list_all(self, include_inactive: bool = False) -> list[JobPosting]:
        """List all active job postings (default)."""
        query = "SELECT * FROM jobs"
        if not include_inactive:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY fetched_at DESC"

        rows = self._conn.execute(query).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_by_company(self, company: str) -> list[JobPosting]:
        """List job postings for a specific company."""
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE company = ? AND is_active = TRUE ORDER BY fetched_at DESC",
            [company],
        ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def search(
        self,
        keywords: str = "",
        location: str = "",
        remote_only: bool = False,
        salary_min: float | None = None,
        salary_max: float | None = None,
        sources: list[JobSource] | None = None,
        limit: int = 25,
    ) -> list[JobPosting]:
        """Search jobs with various filters."""
        conditions = ["is_active = TRUE"]
        params: list[object] = []

        if keywords:
            term = f"%{keywords.lower()}%"
            conditions.append("(LOWER(title) LIKE ? OR LOWER(company) LIKE ?)")
            params.extend([term, term])

        if location:
            term = f"%{location.lower()}%"
            conditions.append("LOWER(location) LIKE ?")
            params.append(term)

        if remote_only:
            conditions.append("remote = TRUE")

        if salary_min is not None:
            conditions.append("salary_min >= ?")
            params.append(salary_min)

        if salary_max is not None:
            conditions.append("salary_max <= ?")
            params.append(salary_max)

        if sources:
            source_values = [s.value for s in sources]
            placeholders = ",".join(["?"] * len(source_values))
            conditions.append(f"source IN ({placeholders})")
            params.extend(source_values)

        query = (
            f"SELECT * FROM jobs WHERE {' AND '.join(conditions)} ORDER BY fetched_at DESC LIMIT ?"
        )
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def mark_inactive(self, job_id: str) -> bool:
        """Mark a job posting as inactive. Returns True if it existed."""
        existing = self.get(job_id)
        if existing is None:
            return False
        self._conn.execute(
            "UPDATE jobs SET is_active = FALSE, last_synced_at = ? WHERE id = ?",
            [datetime.now(UTC).isoformat(), job_id],
        )
        logger.info("job_marked_inactive", id=job_id)
        return True

    def count(self) -> int:
        """Count total active job postings."""
        result = self._conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active = TRUE").fetchone()
        return result[0] if result else 0

    # -- private ----------------------------------------------------------

    def _row_to_job(self, row: tuple[object, ...]) -> JobPosting:
        """Convert a DuckDB row to a JobPosting."""
        (
            id_,
            title,
            company,
            company_id,
            location,
            remote,
            url,
            description,
            description_embedding_json,
            requirements_json,
            benefits_json,
            salary_min,
            salary_max,
            salary_currency,
            required_skills_json,
            experience_level,
            employment_type,
            source,
            posted_date,
            fetched_at,
            last_synced_at,
            is_active,
            metadata_json,
        ) = row

        return JobPosting(
            id=str(id_),
            title=str(title),
            company=str(company),
            company_id=str(company_id or ""),
            location=str(location or ""),
            remote=bool(remote),
            url=str(url or ""),
            description=str(description or ""),
            description_embedding=json.loads(str(description_embedding_json or "[]")),
            requirements=json.loads(str(requirements_json or "[]")),
            benefits=json.loads(str(benefits_json or "[]")),
            salary_min=float(str(salary_min)) if salary_min is not None else None,
            salary_max=float(str(salary_max)) if salary_max is not None else None,
            salary_currency=str(salary_currency or "USD"),
            required_skills=json.loads(str(required_skills_json or "[]")),
            experience_level=str(experience_level or ""),
            employment_type=str(employment_type or "full_time"),
            source=JobSource(str(source)),
            posted_date=_ensure_tz(posted_date) if posted_date else None,
            fetched_at=_ensure_tz(fetched_at),
            last_synced_at=_ensure_tz(last_synced_at),
            is_active=bool(is_active),
            metadata=json.loads(str(metadata_json or "{}")),
        )


def _ensure_tz(value: object) -> datetime:
    """Ensure a value is a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
