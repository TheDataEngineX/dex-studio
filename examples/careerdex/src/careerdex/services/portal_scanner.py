"""Portal scanner - scans company career pages for open positions."""

from __future__ import annotations

import re
import time
from typing import Any

import structlog

from careerdex.models.portal import (
    ScanResult,
    ScanStatus,
    ScanSummary,
    TitleFilter,
)
from careerdex.services.portal_config import get_portal_config, get_title_filter

logger = structlog.get_logger()

__all__ = ["PortalScanner", "scan_portals"]


class PortalScanner:
    """Scanner for company career pages."""

    def __init__(self, title_filter: TitleFilter | None = None):
        self.title_filter = title_filter or get_title_filter()
        self.companies = get_portal_config()

    def _matches_title_filter(self, title: str) -> bool:
        """Check if title matches the positive filter and doesn't match negative."""
        title_lower = title.lower()

        has_positive = any(kw in title_lower for kw in self.title_filter.positive)
        if not has_positive:
            return False

        has_negative = any(kw in title_lower for kw in self.title_filter.negative)
        return not has_negative

    def _extract_title_company_from_search(self, text: str) -> tuple[str, str]:
        """Extract title and company from web search result."""
        patterns = [
            r"(.+?)\s*[@|—–-]\s*(.+?)$",
            r"(.+?)\s+at\s+(.+?)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, text.strip(), re.IGNORECASE)
            if match:
                return match.group(1).strip(), match.group(2).strip()

        return text, "Unknown"

    async def scan_company(self, company: dict[str, Any]) -> list[ScanResult]:
        """Scan a single company's career page."""
        results: list[ScanResult] = []

        careers_url = company.get("careers_url")
        if not careers_url:
            logger.warning("No careers URL for company", company=company.get("name"))
            return results

        ats_platform = company.get("ats_platform", "custom")
        name = company.get("name", "Unknown")

        try:
            if ats_platform == "greenhouse":
                results = await self._scan_greenhouse(careers_url, name)
            elif ats_platform == "ashby":
                results = await self._scan_ashby(careers_url, name)
            elif ats_platform == "lever":
                results = await self._scan_lever(careers_url, name)
            else:
                results = await self._scan_custom(careers_url, name)
        except Exception as e:
            logger.error("Failed to scan company", company=name, error=str(e))

        return results

    async def _scan_greenhouse(self, url: str, company: str) -> list[ScanResult]:
        """Scan Greenhouse API."""
        results: list[ScanResult] = []

        api_url = url.replace("job-boards.greenhouse.io/", "boards-api.greenhouse.io/v1/boards/")
        if "/jobs" not in api_url:
            api_url = f"{api_url}/jobs"

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(api_url, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    jobs = data.get("jobs", [])
                    for job in jobs:
                        title = job.get("title", "")
                        if self._matches_title_filter(title):
                            results.append(
                                ScanResult(
                                    url=job.get("absolute_url", ""),
                                    title=title,
                                    company=company,
                                    source="api",
                                )
                            )
        except Exception as e:
            logger.debug("Greenhouse API failed", url=url, error=str(e))

        return results

    async def _scan_ashby(self, url: str, company: str) -> list[ScanResult]:
        """Scan Ashby jobs page - placeholder for future Playwright integration."""
        return []

    async def _scan_lever(self, url: str, company: str) -> list[ScanResult]:
        """Scan Lever jobs page - placeholder for future Playwright integration."""
        return []

    async def _scan_custom(self, url: str, company: str) -> list[ScanResult]:
        """Scan custom careers page - placeholder for Playwright."""
        return []

    async def scan_all(self) -> tuple[list[ScanResult], ScanSummary]:
        """Scan all configured companies."""
        start_time = time.time()
        all_results: list[ScanResult] = []
        errors: list[str] = []

        for company in self.companies:
            try:
                results = await self.scan_company(company.model_dump())
                all_results.extend(results)
            except Exception as e:
                errors.append(f"{company.name}: {str(e)}")

        filtered = [r for r in all_results if not self._matches_title_filter(r.title)]
        actual_results = [r for r in all_results if self._matches_title_filter(r.title)]

        duration = time.time() - start_time

        summary = ScanSummary(
            companies_scanned=len(self.companies),
            jobs_found=len(all_results),
            jobs_filtered=len(filtered),
            jobs_duplicates=0,
            jobs_added=len(actual_results),
            scan_duration_seconds=duration,
            errors=errors,
        )

        return actual_results, summary

    def filter_results(self, results: list[ScanResult], seen_urls: set[str]) -> list[ScanResult]:
        """Filter out duplicate URLs."""
        filtered = []
        for result in results:
            if result.url in seen_urls:
                result.status = ScanStatus.DUPLICATE
            else:
                result.status = ScanStatus.NEW
                filtered.append(result)
        return filtered


async def scan_portals() -> tuple[list[ScanResult], ScanSummary]:
    """Convenience function to scan all portals."""
    scanner = PortalScanner()
    return await scanner.scan_all()
