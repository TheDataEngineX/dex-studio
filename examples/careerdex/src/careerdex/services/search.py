"""Job search service combining local store + live aggregation."""

import structlog

from careerdex.models.job import JobPosting, JobSearchQuery, JobSource
from careerdex.services.job_store import JobStore

logger = structlog.get_logger()

__all__ = ["JobService"]


class JobService:
    """Job search service combining local store + live aggregation.

    Usage:
        svc = JobService()
        results = svc.search(JobSearchQuery(keywords="data engineer"))
        svc.close()
    """

    def __init__(self, store: JobStore | None = None) -> None:
        self._store = store or JobStore()

    def close(self) -> None:
        self._store.close()

    def search(self, query: JobSearchQuery) -> list[JobPosting]:
        """Search local store for jobs matching query."""
        sources = [JobSource(s) for s in query.sources] if query.sources else None
        return self._store.search(
            keywords=query.keywords,
            location=query.location,
            remote_only=query.remote_only,
            salary_min=query.salary_min,
            salary_max=query.salary_max,
            sources=sources,
            limit=query.max_results,
        )

    def get_by_company(self, company_id: str) -> list[JobPosting]:
        return self._store.list_by_company(company_id)

    def get(self, job_id: str) -> JobPosting | None:
        return self._store.get(job_id)

    async def refresh_source(self, source_name: str, limit: int = 50) -> int:
        """Fetch fresh jobs from a specific source and store them. Returns count of new jobs."""
        from careerdex.services.aggregator import SourceRegistry

        try:
            source_cls = SourceRegistry.get(source_name)
            if source_cls is None:
                logger.warning("source_not_found", source=source_name)
                return 0
            source = source_cls()
            if not hasattr(source, "fetch") or not callable(getattr(source, "fetch", None)):
                logger.warning("source_no_fetch_method", source=source_name)
                return 0
            jobs = (await source.fetch())[:limit]
            count = 0
            for job in jobs:
                self._store.upsert(job)
                count += 1
            logger.info("source_refreshed", source=source_name, jobs=count)
            return count
        except Exception as e:
            logger.warning("source_refresh_failed", source=source_name, error=str(e))
            return 0

    async def refresh_all_sources(self, limit: int = 50) -> dict[str, int]:
        """Refresh all registered sources. Returns dict of source_name -> job count."""
        from careerdex.services.aggregator import SourceRegistry

        results: dict[str, int] = {}
        for source_name in SourceRegistry.list_sources():
            count = await self.refresh_source(source_name, limit)
            if count > 0:
                results[source_name] = count
        return results
