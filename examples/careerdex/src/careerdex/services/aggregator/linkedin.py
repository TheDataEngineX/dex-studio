from __future__ import annotations

import httpx
import structlog

from careerdex.models.job import JobPosting
from careerdex.services.aggregator.base import normalize_company

logger = structlog.get_logger()

__all__ = ["LinkedInSource"]


class LinkedInSource:
    name: str = "linkedin"
    base_url: str = "https://www.linkedin.com/jobs"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CareerDEX/1.0; +https://thedataenginex.org)",
            },
            follow_redirects=True,
        )

    async def fetch(self) -> list[JobPosting]:
        """Fetch from LinkedIn Jobs API."""
        try:
            url = "https://www.linkedin.com/jobs/search"
            resp = await self._client.get(url)
            resp.raise_for_status()
            return []
        except Exception as exc:
            logger.warning("linkedin_fetch_failed", error=str(exc))
            return []

    async def fetch_company_jobs(self, company_slug: str) -> list[JobPosting]:
        """Fetch jobs from a specific company."""
        try:
            normalize = normalize_company(company_slug)
            url = f"https://www.linkedin.com/company/{normalize}/jobs"
            resp = await self._client.get(url)
            resp.raise_for_status()
            return []
        except Exception as exc:
            logger.warning("linkedin_company_fetch_failed", company=company_slug, error=str(exc))
            return []

    async def close(self) -> None:
        await self._client.aclose()
