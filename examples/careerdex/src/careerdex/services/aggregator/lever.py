from __future__ import annotations

import httpx
import structlog

from careerdex.models.job import JobPosting
from careerdex.services.aggregator.normalizer import normalize_job

logger = structlog.get_logger()

__all__ = ["LeverSource"]


class LeverSource:
    name: str = "lever"
    base_url: str = "https://api.lever.co/v0/boards"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "CareerDEX/1.0 (+https://thedataenginex.org)"},
            follow_redirects=True,
        )

    async def fetch(self) -> list[JobPosting]:
        """Fetch from Lever (requires company-specific boards)."""
        return []

    async def fetch_company_jobs(self, company: str) -> list[JobPosting]:
        """Fetch jobs from a specific company Lever board."""
        try:
            url = f"{self.base_url}/{company}/jobs"
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for item in data:
                raw = {
                    "title": item.get("text"),
                    "company": item.get("boardToken", company),
                    "location": item.get("categories", {}).get("location", ""),
                    "url": item.get("hostedUrl"),
                    "description": item.get("descriptionPlain"),
                }
                jobs.append(normalize_job(raw, "lever"))
            return jobs
        except Exception as exc:
            logger.warning("lever_company_fetch_failed", company=company, error=str(exc))
            return []

    async def close(self) -> None:
        await self._client.aclose()
