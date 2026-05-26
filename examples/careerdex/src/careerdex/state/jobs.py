from __future__ import annotations

from typing import Any

import reflex as rx


class JobsState(rx.State):
    query: str = ""
    location: str = ""
    remote_only: bool = False
    results: list[dict[str, Any]] = []
    selected_job: dict[str, Any] = {}
    selected_source: str = "all"
    is_loading: bool = False
    error: str = ""

    @rx.event
    def set_query(self, v: str) -> None:
        self.query = v

    @rx.event
    def set_location(self, v: str) -> None:
        self.location = v

    @rx.event
    def set_remote_only(self, v: bool) -> None:
        self.remote_only = v

    @rx.event
    async def do_search(self) -> Any:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.models.job import JobSearchQuery
            from careerdex.services.search import JobService

            svc = JobService()
            q = JobSearchQuery(
                keywords=self.query,
                location=self.location,
                remote_only=self.remote_only,
                max_results=50,
            )
            jobs = svc.search(q)
            self.results = [j.model_dump() for j in jobs]
            svc.close()
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def refresh_all(self) -> Any:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.models.job import JobSearchQuery
            from careerdex.services.search import JobService

            svc = JobService()
            counts = await svc.refresh_all_sources(limit=50)
            jobs = svc.search(JobSearchQuery(keywords=self.query, max_results=50))
            self.results = [j.model_dump() for j in jobs]
            svc.close()
            self.error = f"Refreshed: {', '.join(f'{k}: {v}' for k, v in counts.items())}"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def select_job(self, job: dict[str, Any]) -> None:
        self.selected_job = job

    @rx.event
    async def save_job(self, job: dict[str, Any]) -> Any:
        self.is_loading = True
        yield
        try:
            from careerdex.models.application import ApplicationEntry
            from careerdex.services.tracker import ApplicationTracker

            tracker = ApplicationTracker()
            entry = ApplicationEntry(
                company=job.get("company", ""),
                position=job.get("title", ""),
                url=job.get("url", ""),
                location=job.get("location", ""),
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                source=job.get("source", ""),
            )
            tracker.add(entry)
            tracker.close()
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False
