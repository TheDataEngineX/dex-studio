from __future__ import annotations

import httpx
import structlog

from careerdex.models.job import JobPosting

logger = structlog.get_logger()

__all__ = ["IndeedSource"]


class IndeedSource:
    name: str = "indeed"
    base_url: str = "https://www.indeed.com"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CareerDEX/1.0; +https://thedataenginex.org)",
            },
            follow_redirects=True,
        )

    async def fetch(self) -> list[JobPosting]:
        """Fetch from Indeed API."""
        try:
            url = "https://www.indeed.com/jobs"
            resp = await self._client.get(url)
            resp.raise_for_status()
            return []
        except Exception as exc:
            logger.warning("indeed_fetch_failed", error=str(exc))
            return []

    async def fetch_company_jobs(self, company_name: str) -> list[JobPosting]:
        """Search jobs by company name."""
        try:
            params = {"q": company_name, "fromage": "3"}
            url = "https://www.indeed.com/jobs"
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return []
        except Exception as exc:
            logger.warning("indeed_company_fetch_failed", company=company_name, error=str(exc))
            return []

    async def close(self) -> None:
        await self._client.aclose()
