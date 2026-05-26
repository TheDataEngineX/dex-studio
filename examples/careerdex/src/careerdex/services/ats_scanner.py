"""ATS Scanner — targeted company portal scanning via public ATS APIs.

Inspired by career-ops (github.com/santifer/career-ops).
Directly queries Greenhouse / Ashby / Lever APIs — no auth, no scraping.

Public API endpoints (GET, no auth required):
  Greenhouse  https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
  Ashby       https://api.ashbyhq.com/posting-api/job-board/{id}?includeCompensation=true
  Lever       https://api.lever.co/v0/postings/{company_id}?mode=json
"""

from __future__ import annotations

import contextlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import httpx
import structlog

from careerdex.models.job import ATSType, JobPosting, JobSource, TrackedCompany

logger = structlog.get_logger(__name__)

__all__ = ["ATSScanService"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "ats_scanner.duckdb"

_GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
_ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{id}?includeCompensation=true"
_LEVER_URL = "https://api.lever.co/v0/postings/{company_id}?mode=json"

# Regex → (pattern, ats_type) — ordered most-specific first
_ATS_PATTERNS: list[tuple[re.Pattern[str], ATSType]] = [
    (re.compile(r"(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)"), ATSType.GREENHOUSE),
    (re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)"), ATSType.ASHBY),
    (re.compile(r"jobs\.lever\.co/([^/?#]+)"), ATSType.LEVER),
]

# Seed companies — data / AI / ML focused; all confirmed on these ATS platforms
_DEFAULT_COMPANIES: list[dict[str, str]] = [
    {
        "name": "Anthropic",
        "careers_url": "https://job-boards.greenhouse.io/anthropic",
        "ats_type": "greenhouse",
        "ats_id": "anthropic",
    },
    {
        "name": "Scale AI",
        "careers_url": "https://job-boards.greenhouse.io/scaleai",
        "ats_type": "greenhouse",
        "ats_id": "scaleai",
    },
    {
        "name": "Cohere",
        "careers_url": "https://job-boards.greenhouse.io/cohere",
        "ats_type": "greenhouse",
        "ats_id": "cohere",
    },
    {
        "name": "dbt Labs",
        "careers_url": "https://job-boards.greenhouse.io/dbtlabs",
        "ats_type": "greenhouse",
        "ats_id": "dbtlabs",
    },
    {
        "name": "Weights & Biases",
        "careers_url": "https://job-boards.greenhouse.io/wandb",
        "ats_type": "greenhouse",
        "ats_id": "wandb",
    },
    {
        "name": "Hugging Face",
        "careers_url": "https://job-boards.greenhouse.io/huggingface",
        "ats_type": "greenhouse",
        "ats_id": "huggingface",
    },
    {
        "name": "Airbyte",
        "careers_url": "https://jobs.ashbyhq.com/airbyte",
        "ats_type": "ashby",
        "ats_id": "airbyte",
    },
    {
        "name": "Modal",
        "careers_url": "https://jobs.ashbyhq.com/modal-labs",
        "ats_type": "ashby",
        "ats_id": "modal-labs",
    },
    {
        "name": "Mistral AI",
        "careers_url": "https://jobs.lever.co/mistral",
        "ats_type": "lever",
        "ats_id": "mistral",
    },
]

# Title keywords — positive AND negative — same approach as career-ops
_POSITIVE_KEYWORDS = [
    "data engineer",
    "data platform",
    "analytics engineer",
    "ml engineer",
    "machine learning",
    "ai engineer",
    "llm",
    "mlops",
    "dataops",
    "platform engineer",
    "backend engineer",
    "python",
    "spark",
    "dbt",
    "airflow",
    "kafka",
    "senior",
    "staff",
    "principal",
    "lead",
]
_NEGATIVE_KEYWORDS = [
    "intern",
    "junior",
    ".net",
    "java developer",
    "php",
    "blockchain",
    "crypto",
    "sap",
    "mainframe",
    "sales",
    "account executive",
    "recruiter",
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _detect_ats(url: str) -> tuple[ATSType, str]:
    """Return (ats_type, slug) from a careers page URL. Slug is '' if undetected."""
    for pattern, ats_type in _ATS_PATTERNS:
        m = pattern.search(url)
        if m:
            return ats_type, m.group(1)
    return ATSType.UNKNOWN, ""


def _title_matches(title: str) -> bool:
    """Return True if title passes positive/negative keyword filter."""
    low = title.lower()
    if any(kw in low for kw in _NEGATIVE_KEYWORDS):
        return False
    return any(kw in low for kw in _POSITIVE_KEYWORDS)


class ATSScanService:
    """Scan tracked company ATS portals for live job postings.

    Usage::

        svc = ATSScanService()
        new_jobs = svc.scan_all(filter_titles=True)
        svc.close()
    """

    def __init__(self, db_path: Path | None = None, timeout: float = 10.0) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "DEX-Studio/0.2 (ats-scan; +https://thedataenginex.org)"},
            follow_redirects=True,
        )
        self._init_tables()
        self._seed_defaults()
        logger.info("ats_scanner_ready", db=str(self._db_path))

    # -- Setup ----------------------------------------------------------------

    def _init_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                careers_url VARCHAR DEFAULT '',
                ats_type VARCHAR DEFAULT 'unknown',
                ats_id VARCHAR DEFAULT '',
                enabled BOOLEAN DEFAULT true,
                added_at TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_history (
                url VARCHAR PRIMARY KEY,
                title VARCHAR DEFAULT '',
                company VARCHAR DEFAULT '',
                first_seen TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_searches (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                params_json VARCHAR NOT NULL,
                created_at TIMESTAMP
            )
        """)

    def _seed_defaults(self) -> None:
        count = self._conn.execute("SELECT COUNT(*) FROM companies").fetchone()
        if count is not None and count[0] > 0:
            return
        for c in _DEFAULT_COMPANIES:
            company = TrackedCompany(
                name=c["name"],
                careers_url=c["careers_url"],
                ats_type=ATSType(c["ats_type"]),
                ats_id=c["ats_id"],
            )
            self._upsert_company(company)
        logger.info("ats_defaults_seeded", count=len(_DEFAULT_COMPANIES))

    # -- Company management ---------------------------------------------------

    def _upsert_company(self, company: TrackedCompany) -> None:
        self._conn.execute(
            """
            INSERT INTO companies (id, name, careers_url, ats_type, ats_id, enabled, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                careers_url = excluded.careers_url,
                ats_type = excluded.ats_type,
                ats_id = excluded.ats_id,
                enabled = excluded.enabled
            """,
            [
                company.id,
                company.name,
                company.careers_url,
                company.ats_type.value,
                company.ats_id,
                company.enabled,
                company.added_at.isoformat(),
            ],
        )

    def add_company(self, name: str, careers_url: str) -> TrackedCompany:
        """Add a company by URL — auto-detects ATS type and slug."""
        ats_type, ats_id = _detect_ats(careers_url)
        company = TrackedCompany(
            name=name,
            careers_url=careers_url,
            ats_type=ats_type,
            ats_id=ats_id,
        )
        self._upsert_company(company)
        logger.info("company_added", name=name, ats_type=ats_type, ats_id=ats_id)
        return company

    def remove_company(self, company_id: str) -> None:
        self._conn.execute("DELETE FROM companies WHERE id = ?", [company_id])

    def toggle_company(self, company_id: str, enabled: bool) -> None:
        self._conn.execute("UPDATE companies SET enabled = ? WHERE id = ?", [enabled, company_id])

    def list_companies(self) -> list[TrackedCompany]:
        rows = self._conn.execute(
            "SELECT id, name, careers_url, ats_type, ats_id, enabled, added_at "
            "FROM companies ORDER BY name"
        ).fetchall()
        return [
            TrackedCompany(
                id=str(row[0]),
                name=str(row[1]),
                careers_url=str(row[2]),
                ats_type=ATSType(str(row[3])),
                ats_id=str(row[4]),
                enabled=bool(row[5]),
                added_at=datetime.fromisoformat(str(row[6])),
            )
            for row in rows
        ]

    # -- Scanning -------------------------------------------------------------

    def scan_company(
        self, company: TrackedCompany, filter_titles: bool = True
    ) -> tuple[list[JobPosting], list[JobPosting]]:
        """Scan a single company's ATS portal.

        Returns (new_jobs, all_jobs) — new_jobs are URLs not seen in scan_history.
        """
        if company.ats_type == ATSType.GREENHOUSE:
            all_jobs = self._fetch_greenhouse(company)
        elif company.ats_type == ATSType.ASHBY:
            all_jobs = self._fetch_ashby(company)
        elif company.ats_type == ATSType.LEVER:
            all_jobs = self._fetch_lever(company)
        else:
            logger.warning("ats_unknown_type", company=company.name, url=company.careers_url)
            return [], []

        if filter_titles:
            all_jobs = [j for j in all_jobs if _title_matches(j.title)]

        seen_urls = self._load_seen_urls({j.url for j in all_jobs})
        new_jobs = [j for j in all_jobs if j.url not in seen_urls]

        # Record new URLs in scan history
        now = datetime.now(UTC).isoformat()
        for job in new_jobs:
            if job.url:
                self._conn.execute(
                    "INSERT INTO scan_history (url, title, company, first_seen) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT (url) DO NOTHING",
                    [job.url, job.title, job.company, now],
                )

        logger.info(
            "company_scanned",
            company=company.name,
            total=len(all_jobs),
            new=len(new_jobs),
        )
        return new_jobs, all_jobs

    def scan_all(self, filter_titles: bool = True) -> tuple[list[JobPosting], list[JobPosting]]:
        """Scan all enabled companies. Returns (new_jobs, all_jobs)."""
        all_new: list[JobPosting] = []
        all_total: list[JobPosting] = []
        for company in self.list_companies():
            if not company.enabled:
                continue
            new, total = self.scan_company(company, filter_titles=filter_titles)
            all_new.extend(new)
            all_total.extend(total)
        logger.info("scan_all_complete", new=len(all_new), total=len(all_total))
        return all_new, all_total

    def _load_seen_urls(self, urls: set[str]) -> set[str]:
        if not urls:
            return set()
        placeholders = ", ".join("?" * len(urls))
        rows = self._conn.execute(
            f"SELECT url FROM scan_history WHERE url IN ({placeholders})", list(urls)
        ).fetchall()
        return {str(r[0]) for r in rows}

    # -- ATS fetchers ---------------------------------------------------------

    def _fetch_greenhouse(self, company: TrackedCompany) -> list[JobPosting]:
        url = _GREENHOUSE_URL.format(slug=company.ats_id)
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("greenhouse_fetch_failed", company=company.name, error=str(exc))
            return []

        jobs: list[JobPosting] = []
        for item in data.get("jobs", []):
            location_obj = item.get("location") or {}
            location = (
                location_obj.get("name", "")
                if isinstance(location_obj, dict)
                else str(location_obj)
            )
            updated_raw = item.get("updated_at", "")
            posted: datetime | None = None
            if updated_raw:
                with contextlib.suppress(ValueError):
                    posted = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
            jobs.append(
                JobPosting(
                    title=str(item.get("title", "")),
                    company=company.name,
                    location=location,
                    remote="remote" in location.lower(),
                    url=str(item.get("absolute_url", "")),
                    source=JobSource.GREENHOUSE,
                    posted_date=posted,
                )
            )
        logger.info("greenhouse_fetched", company=company.name, count=len(jobs))
        return jobs

    def _fetch_ashby(self, company: TrackedCompany) -> list[JobPosting]:
        url = _ASHBY_URL.format(id=company.ats_id)
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("ashby_fetch_failed", company=company.name, error=str(exc))
            return []

        jobs: list[JobPosting] = []
        for item in data.get("jobs", []):
            location = str(item.get("location") or item.get("locationName") or "")
            published_raw = item.get("publishedDate", "")
            posted: datetime | None = None
            if published_raw:
                with contextlib.suppress(ValueError):
                    posted = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00"))
            compensation = str(item.get("compensationTierSummary") or "")
            jobs.append(
                JobPosting(
                    title=str(item.get("title", "")),
                    company=company.name,
                    location=location,
                    remote="remote" in location.lower(),
                    url=str(item.get("jobUrl", "")),
                    description=compensation[:200] if compensation else "",
                    source=JobSource.ASHBY,
                    posted_date=posted,
                )
            )
        logger.info("ashby_fetched", company=company.name, count=len(jobs))
        return jobs

    def _fetch_lever(self, company: TrackedCompany) -> list[JobPosting]:
        url = _LEVER_URL.format(company_id=company.ats_id)
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data: list[Any] = resp.json()
        except Exception as exc:
            logger.warning("lever_fetch_failed", company=company.name, error=str(exc))
            return []

        if not isinstance(data, list):
            return []

        jobs: list[JobPosting] = []
        for item in data:
            categories = item.get("categories") or {}
            location = str(categories.get("location", "")) if isinstance(categories, dict) else ""
            created_ms = item.get("createdAt")
            posted: datetime | None = None
            if created_ms:
                with contextlib.suppress(ValueError, OSError):
                    posted = datetime.fromtimestamp(int(created_ms) / 1000, tz=UTC)
            description_raw = item.get("descriptionPlain") or item.get("description") or ""
            jobs.append(
                JobPosting(
                    title=str(item.get("text", "")),
                    company=company.name,
                    location=location,
                    remote="remote" in location.lower(),
                    url=str(item.get("hostedUrl", "")),
                    description=_strip_html(str(description_raw))[:300],
                    source=JobSource.LEVER,
                    posted_date=posted,
                )
            )
        logger.info("lever_fetched", company=company.name, count=len(jobs))
        return jobs

    # -- Saved searches -------------------------------------------------------

    def save_search(self, name: str, params: dict[str, Any]) -> str:
        """Persist a named search. Returns the new ID."""
        sid = uuid4().hex[:8]
        self._conn.execute(
            "INSERT INTO saved_searches (id, name, params_json, created_at) VALUES (?, ?, ?, ?)",
            [sid, name, json.dumps(params), datetime.now(UTC).isoformat()],
        )
        logger.info("search_saved", name=name, id=sid)
        return sid

    def list_saved_searches(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, name, params_json, created_at FROM saved_searches ORDER BY created_at DESC"
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                params: dict[str, Any] = json.loads(str(r[2]))
            except Exception:
                params = {}
            out.append(
                {
                    "id": str(r[0]),
                    "name": str(r[1]),
                    "params": params,
                    "created_at": str(r[3]),
                }
            )
        return out

    def delete_saved_search(self, search_id: str) -> None:
        self._conn.execute("DELETE FROM saved_searches WHERE id = ?", [search_id])

    # -- Lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._client.close()
        if self._conn:
            self._conn.close()

    def __enter__(self) -> ATSScanService:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
