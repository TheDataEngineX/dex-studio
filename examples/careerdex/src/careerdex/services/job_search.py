"""Job search service — multiple public APIs.

Sources (all free, no auth required unless noted):
- Remotive API (remotive.com) — remote jobs, JSON
- Arbeitnow API (arbeitnow.com) — global jobs, JSON

Other sources (require API keys):
- Jooble API (jooble.org) — set _JOBBLE_API_KEY for more results
- USAJobs API (usajobs.gov) — government jobs, requires API key

Note: Many job boards block RSS/scraping. These APIs are designed for programmatic access.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import structlog

from careerdex.models.job import JobPosting, JobSearchQuery, JobSource

logger = structlog.get_logger()

__all__ = ["JobSearchService"]

# API endpoints
_REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
_ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
_JOBBLE_URL = "https://jooble.org/api/{api_key}"
_JOBBLE_API_KEY = ""  # Optional: set your key at jooble.org/developers

# Salary parsing pattern
_SALARY_RE = re.compile(
    r"[\$£€]?\s*(\d[\d,]*\.?\d*)\s*[kK]?\s*[-–—]\s*[\$£€]?\s*(\d[\d,]*\.?\d*)\s*[kK]?",
    re.IGNORECASE,
)


def _parse_salary(text: str) -> tuple[float | None, float | None]:
    """Extract salary range from free text. Returns (min, max) or (None, None)."""
    m = _SALARY_RE.search(text)
    if not m:
        return None, None
    try:
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        # Detect 'k' notation
        if "k" in text[m.start() : m.end()].lower():
            lo *= 1000
            hi *= 1000
        return lo, hi
    except ValueError:
        return None, None


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_rss_date(date_str: str | None) -> datetime | None:
    """Parse RFC 2822 / ISO 8601 date string to UTC datetime."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).astimezone(UTC)
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None


class JobSearchService:
    """Fetches job postings from multiple sources.

    All HTTP calls use a single shared httpx client for connection reuse.
    RSS parsing uses feedparser (optional dep) with graceful fallback.

    Usage::

        svc = JobSearchService()
        results = svc.search(JobSearchQuery(keywords="data engineer", remote_only=True))
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "DEX-Studio/0.2 (job-search; +https://thedataenginex.org)"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> JobSearchService:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- Public API -------------------------------------------------------

    def search(self, query: JobSearchQuery) -> list[JobPosting]:
        """Run a search across all configured sources and return deduplicated results."""
        results: list[JobPosting] = []

        # Search Remotive (main source for remote jobs)
        results.extend(self._search_remotive(query))

        # Search Arbeitnow (global jobs database)
        results.extend(self._search_arbeitnow(query))

        # Search Jooble if API key is configured
        if _JOBBLE_API_KEY:
            results.extend(self._search_jooble(query))

        # Deduplicate by URL (keep first occurrence)
        seen: set[str] = set()
        unique: list[JobPosting] = []
        for job in results:
            key = job.url.lower().strip() if job.url else job.id
            if key not in seen:
                seen.add(key)
                unique.append(job)

        # Client-side filters
        unique = _apply_filters(unique, query)

        return unique[: query.max_results]

    # -- Remotive ---------------------------------------------------------

    def _search_remotive(self, query: JobSearchQuery) -> list[JobPosting]:
        """Fetch from Remotive public JSON API."""
        params: dict[str, str | int] = {"limit": query.max_results * 2}
        if query.keywords:
            params["search"] = query.keywords

        try:
            resp = self._client.get(_REMOTIVE_URL, params=params)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("remotive_fetch_failed", error=str(exc))
            return []

        jobs: list[JobPosting] = []
        for item in data.get("jobs", []):
            sal_min, sal_max = _parse_salary(item.get("salary", ""))
            posted = _parse_rss_date(item.get("publication_date"))
            tags = item.get("tags", [])
            skills = [t for t in tags if isinstance(t, str)][:8] if tags else []
            jobs.append(
                JobPosting(
                    title=item.get("title", "") or item.get("job_title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("candidate_required_location", "Worldwide"),
                    remote=True,
                    url=item.get("url", ""),
                    description=_strip_html(item.get("description", ""))[:500],
                    salary_min=sal_min,
                    salary_max=sal_max,
                    salary_currency="USD",
                    required_skills=skills,
                    employment_type=item.get("job_type", "full_time"),
                    source=JobSource.REMOTIVE_API,
                    posted_date=posted,
                )
            )

        logger.info("remotive_fetched", count=len(jobs))
        return jobs

    # -- Jooble -----------------------------------------------------------

    def _search_jooble(self, query: JobSearchQuery) -> list[JobPosting]:
        """Fetch from Jooble public API."""
        try:
            payload = {
                "keywords": query.keywords,
                "location": query.location or "",
                "pageSize": min(query.max_results, 20),
            }
            if query.remote_only:
                payload["remote"] = True
            resp = self._client.post(
                _JOBBLE_URL.format(api_key=_JOBBLE_API_KEY),
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("jooble_fetch_failed", error=str(exc))
            return []

        jobs: list[JobPosting] = []
        for item in data.get("jobs", []):
            sal_min, sal_max = _parse_salary(item.get("salary", ""))
            posted = _parse_rss_date(item.get("publicationDate"))
            jobs.append(
                JobPosting(
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    remote=query.remote_only,
                    url=item.get("link", ""),
                    description=_strip_html(item.get("snippet", ""))[:500],
                    salary_min=sal_min,
                    salary_max=sal_max,
                    source=JobSource.RSS_LINKEDIN,
                    posted_date=posted,
                )
            )

        logger.info("jooble_fetched", count=len(jobs))
        return jobs

    # -- Arbeitnow ---------------------------------------------------------

    def _search_arbeitnow(self, query: JobSearchQuery) -> list[JobPosting]:
        """Fetch from Arbeitnow job board API."""
        try:
            resp = self._client.get(_ARBEITNOW_URL, timeout=30.0)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("arbeitnow_fetch_failed", error=str(exc))
            return []

        jobs: list[JobPosting] = []
        for item in data.get("data", []):
            title = item.get("title", "")
            company = item.get("company_name", "")
            desc = _strip_html(item.get("description", ""))[:500]

            # Parse job types
            job_types = item.get("job_types", []) or []
            emp_type = job_types[0] if job_types else "full_time"
            if isinstance(emp_type, list):
                emp_type = emp_type[0] if emp_type else "full_time"

            # Parse posted date
            created_at = item.get("created_at", "")
            posted = _parse_rss_date(created_at)

            # Extract skills from tags
            tags = item.get("tags", []) or []
            skills = [t for t in tags if isinstance(t, str)][:8]

            # Build URL
            slug = item.get("slug", "")
            job_url = f"https://www.arbeitnow.com/job/{slug}" if slug else ""

            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=item.get("location", "Remote"),
                    remote=bool(item.get("remote")),
                    url=job_url,
                    description=desc,
                    required_skills=skills,
                    employment_type=emp_type,
                    source=JobSource.RSS_REMOTEOK,  # reuse enum
                    posted_date=posted,
                )
            )

        logger.info("arbeitnow_fetched", count=len(jobs))
        return jobs


# -- Helpers --------------------------------------------------------------


_US_ALIASES: frozenset[str] = frozenset(
    {"us", "usa", "united states", "united states of america", "america"}
)
_US_STATE_ABBREVS: frozenset[str] = frozenset(
    {
        ", al",
        ", ak",
        ", az",
        ", ar",
        ", ca",
        ", co",
        ", ct",
        ", de",
        ", fl",
        ", ga",
        ", hi",
        ", id",
        ", il",
        ", in",
        ", ia",
        ", ks",
        ", ky",
        ", la",
        ", me",
        ", md",
        ", ma",
        ", mi",
        ", mn",
        ", ms",
        ", mo",
        ", mt",
        ", ne",
        ", nv",
        ", nh",
        ", nj",
        ", nm",
        ", ny",
        ", nc",
        ", nd",
        ", oh",
        ", ok",
        ", or",
        ", pa",
        ", ri",
        ", sc",
        ", sd",
        ", tn",
        ", tx",
        ", ut",
        ", vt",
        ", va",
        ", wa",
        ", wv",
        ", wi",
        ", wy",
        ", dc",
    }
)


def _is_us_location(loc: str) -> bool:
    loc_l = loc.lower()
    return any(alias in loc_l for alias in _US_ALIASES) or any(
        abbrev in loc_l for abbrev in _US_STATE_ABBREVS
    )


def _apply_filters(jobs: list[JobPosting], query: JobSearchQuery) -> list[JobPosting]:
    """Apply client-side filters that APIs don't support natively."""
    from datetime import UTC, timedelta

    out = jobs
    # Keyword filter — match all terms against title + description + skills
    if query.keywords:
        kw_terms = query.keywords.lower().split()
        out = [
            j
            for j in out
            if all(
                term in j.title.lower()
                or term in j.description.lower()
                or term in " ".join(j.required_skills).lower()
                for term in kw_terms
            )
        ]
    # Location filter — handles US aliases and state abbreviations
    if query.location:
        loc_lower = query.location.lower().strip()
        if loc_lower in _US_ALIASES:
            out = [j for j in out if _is_us_location(j.location)]
        else:
            out = [
                j
                for j in out
                if loc_lower in j.location.lower()
                or loc_lower in j.title.lower()
                or loc_lower in j.company.lower()
            ]
    # Remote only filter
    if query.remote_only:
        out = [j for j in out if j.remote]
    # Salary min filter
    if query.salary_min is not None:
        out = [j for j in out if j.salary_max is None or j.salary_max >= query.salary_min]
    # Salary max filter
    if query.salary_max is not None:
        out = [j for j in out if j.salary_min is None or j.salary_min <= query.salary_max]
    # Experience level filter
    if query.experience_level:
        level = query.experience_level.lower()
        out = [j for j in out if not j.experience_level or j.experience_level.lower() == level]
    # Employment type filter
    if query.employment_type:
        emp_type = query.employment_type.lower()
        out = [j for j in out if not j.employment_type or j.employment_type.lower() == emp_type]
    # Date posted filter
    if query.date_posted and query.date_posted != "all":
        now = datetime.now(UTC)
        cutoff: datetime | None = None
        if query.date_posted == "day":
            cutoff = now - timedelta(days=1)
        elif query.date_posted == "3days":
            cutoff = now - timedelta(days=3)
        elif query.date_posted == "week":
            cutoff = now - timedelta(weeks=1)
        elif query.date_posted == "month":
            cutoff = now - timedelta(days=30)
        if cutoff:
            out = [
                j
                for j in out
                if j.posted_date is None or _normalize_to_utc(j.posted_date) >= cutoff
            ]
    return out


def _normalize_to_utc(dt: datetime) -> datetime:
    """Normalize datetime to UTC, handling both naive and aware datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
