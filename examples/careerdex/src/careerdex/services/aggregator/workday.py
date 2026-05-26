from __future__ import annotations

import httpx
import structlog

from careerdex.models.job import JobPosting
from careerdex.services.aggregator.base import normalize_company

logger = structlog.get_logger()

__all__ = ["WorkdaySource"]


class WorkdaySource:
    name: str = "workday"
    base_url: str = "https://{company}.workday.com/careers"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CareerDEX/1.0; +https://thedataenginex.org)",
            },
            follow_redirects=True,
        )

    async def fetch(self) -> list[JobPosting]:
        """Fetch from Workday (requires company-specific URLs)."""
        return []

    async def fetch_company_jobs(self, company_slug: str) -> list[JobPosting]:
        """Fetch jobs from a specific Workday career page."""
        try:
            normalized = normalize_company(company_slug)
            url = f"https://{normalized}.workday.com/careers"
            resp = await self._client.get(url)
            resp.raise_for_status()
            logger.info("workday_fetched", company=company_slug)
            return []
        except Exception as exc:
            logger.warning("workday_fetch_blocked", company=company_slug, error=str(exc))
            return []

    async def close(self) -> None:
        await self._client.aclose()
