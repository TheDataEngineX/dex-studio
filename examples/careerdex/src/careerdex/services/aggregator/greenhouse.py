from __future__ import annotations

import httpx
import structlog

from careerdex.models.job import JobPosting
from careerdex.services.aggregator.normalizer import normalize_job

logger = structlog.get_logger()

__all__ = ["GreenhouseSource"]


class GreenhouseSource:
    name: str = "greenhouse"
    base_url: str = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "CareerDEX/1.0 (+https://thedataenginex.org)"},
            follow_redirects=True,
        )

    async def fetch(self) -> list[JobPosting]:
        """Fetch from all configured Greenhouse boards."""
        try:
            url = f"{self.base_url}/_remotive/jobs"
            resp = await self._client.get(url)
            resp.raise_for_status()
            return []
        except Exception as exc:
            logger.warning("greenhouse_fetch_failed", error=str(exc))
            return []

    async def fetch_company_jobs(self, board_token: str) -> list[JobPosting]:
        """Fetch jobs from a specific company board."""
        try:
            url = f"{self.base_url}/{board_token}/jobs"
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for item in data.get("jobs", []):
                raw = {
                    "title": item.get("title"),
                    "company": item.get("board_token"),
                    "location": item.get("location", {}).get("name", ""),
                    "url": item.get("absolute_url"),
                    "description": item.get("content"),
                }
                jobs.append(normalize_job(raw, "greenhouse"))
            return jobs
        except Exception as exc:
            logger.warning("greenhouse_company_fetch_failed", board=board_token, error=str(exc))
            return []

    async def close(self) -> None:
        await self._client.aclose()
