from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

import reflex as rx

# Try to import DataEngineX audit logging
try:
    from dataenginex.services.career_audit import get_career_audit

    AUDIT_AVAILABLE = True
except ImportError:
    try:
        from careerdex.services.career_audit import get_career_audit

        AUDIT_AVAILABLE = True
    except ImportError:
        AUDIT_AVAILABLE = False
        get_career_audit = None


def _audit_log(action: str, **kwargs: Any) -> None:
    if get_career_audit:
        with suppress(Exception):
            get_career_audit().log(action, **kwargs)


class CareerState(rx.State):
    """Global state for all career pages."""

    # Core data
    applications: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    progress_data: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []

    # Resume + matching
    resume_sections: dict[str, Any] = {}
    match_results: list[dict[str, Any]] = []
    ats_results: dict[str, Any] = {}

    # Interview prep
    interview_questions: list[dict[str, Any]] = []
    story_bank: list[dict[str, Any]] = []

    # Networking
    network_contacts: list[dict[str, Any]] = []

    # Job search
    search_query: str = ""
    search_results: list[dict[str, Any]] = []

    # Analytics
    funnel_data: dict[str, Any] = {}
    offer_comparisons: list[dict[str, Any]] = []

    # Cover letter
    cover_letter_result: dict[str, Any] = {}
    cover_letter_company: str = ""
    cover_letter_job_title: str = ""

    # Scanner
    scan_results: list[dict[str, Any]] = []

    # Company research
    research_result: dict[str, Any] = {}
    research_company_name: str = ""

    # Job evaluation
    evaluation_result: dict[str, Any] = {}
    evaluation_job_desc: str = ""

    # Batch processing
    batch_jobs: list[dict[str, Any]] = []
    batch_url_input: str = ""
    batch_company_input: str = ""
    batch_role_input: str = ""

    # Job Channels
    job_sources: list[str] = []
    job_source_stats: dict[str, int] = {}
    selected_job_source: str = ""

    # UI state
    is_loading: bool = False
    error: str = ""
    notification: str = ""
    selected_application_id: str = ""
    selected_job_url: str = ""
    resume_text: str = ""
    job_description: str = ""

    @rx.event
    async def init(self) -> AsyncGenerator[None]:
        """Load core data on page mount."""
        async for _ in self.load_applications():
            yield

    # -----------------------------------------------------------------------
    # Applications
    # -----------------------------------------------------------------------

    @rx.event
    async def load_applications(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.tracker import ApplicationTracker

            tracker = ApplicationTracker()
            self.applications = [a.model_dump() for a in tracker.list_all()]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def add_application(self, company: str, role: str, url: str = "") -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.models.application import ApplicationEntry
            from careerdex.services.tracker import ApplicationTracker

            tracker = ApplicationTracker()
            entry = ApplicationEntry(company=company, position=role, url=url)
            tracker.add(entry)
            _audit_log("application_added", company=company, role=role, details=url)
            self.notification = f"Added: {company} — {role}"
            async for _ in self.load_applications():
                yield
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def update_application_status(self, app_id: str, status: str) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.models.application import ApplicationStatus
            from careerdex.services.tracker import ApplicationTracker

            tracker = ApplicationTracker()
            tracker.update_status(app_id, ApplicationStatus(status))
            async for _ in self.load_applications():
                yield
            self.notification = f"Status updated: {status}"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def select_application(self, app_id: str) -> None:
        self.selected_application_id = app_id

    @rx.var
    def selected_application(self) -> dict[str, Any]:
        for a in self.applications:
            if a.get("id") == self.selected_application_id:
                return a
        return {}

    # -----------------------------------------------------------------------
    # Job search
    # -----------------------------------------------------------------------

    @rx.event
    async def search_jobs(self) -> AsyncGenerator[None]:
        if not self.search_query.strip():
            return
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.models.job import JobSearchQuery
            from careerdex.services.job_search import JobSearchService

            svc = JobSearchService()
            results = svc.search(JobSearchQuery(keywords=self.search_query))
            self.search_results = [r.model_dump() for r in results]
            _audit_log("job_search", details=self.search_query, status=str(len(results)))
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def set_search_query(self, v: str) -> None:
        self.search_query = v

    @rx.event
    async def load_cached_jobs(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.services.job_cache import JobCacheService

            with JobCacheService() as cache:
                postings = cache.recent()
            self.jobs = [p.model_dump() for p in postings]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def set_selected_job_url(self, url: str) -> None:
        self.selected_job_url = url

    @rx.event
    async def load_jobs(self) -> AsyncGenerator[None]:
        """Alias for load_cached_jobs - loads jobs from cache."""
        async for _ in self.load_cached_jobs():
            yield

    @rx.event
    async def load_job_channels(self) -> AsyncGenerator[None]:
        """Load job sources/channels for job channels view."""
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.job_cache import JobCacheService

            with JobCacheService() as cache:
                sources = cache.sources()
                source_stats = cache.stats()
            self.job_sources = sources
            self.job_source_stats = source_stats
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def scan_portals(self) -> AsyncGenerator[None]:
        """Scan all pre-configured company portals."""
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.portal_config import DEFAULT_COMPANIES

            self.scan_results = [
                {
                    "name": c.name,
                    "industry": c.industry,
                    "ats_platform": c.ats_platform.value,
                    "careers_url": c.careers_url,
                    "is_active": True,
                }
                for c in DEFAULT_COMPANIES[:20]
            ]
            self.notification = f"Loaded {len(self.scan_results)} portals"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    # -----------------------------------------------------------------------
    # Resume + ATS
    # -----------------------------------------------------------------------

    @rx.event
    def set_resume_text(self, text: str) -> None:
        self.resume_text = text

    @rx.event
    def set_job_description(self, text: str) -> None:
        self.job_description = text

    @rx.event
    async def match_resume(self) -> AsyncGenerator[None]:
        if not self.resume_text or not self.job_description:
            self.error = "Provide both resume text and job description"
            return
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.resume_matcher import ResumeMatcher

            matcher = ResumeMatcher()
            result = matcher.match_text(self.resume_text, self.job_description)
            suggestions = result.suggestions if hasattr(result, "suggestions") else None
            self.match_results = suggestions or [result.model_dump()]
            self.notification = f"Match score: {getattr(result, 'score', 'N/A')}"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def scan_ats(self) -> AsyncGenerator[None]:
        if not self.resume_text:
            self.error = "Provide resume text first"
            return
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.ats_scanner import ATSScanner

            scanner = ATSScanner()
            result = scanner.scan(self.resume_text)
            self.ats_results = (
                result.model_dump() if hasattr(result, "model_dump") else {"result": str(result)}
            )
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    # -----------------------------------------------------------------------
    # Interview prep
    # -----------------------------------------------------------------------

    @rx.event
    async def load_interview_questions(self, role: str = "") -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.services.interview_prep import InterviewPrepService

            svc = InterviewPrepService()
            questions = svc.get_questions(role=role) if role else svc.get_all_questions()
            self.interview_questions = [
                q.model_dump() if hasattr(q, "model_dump") else {"text": str(q)} for q in questions
            ]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def load_story_bank(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.services.story_bank import StoryBankService

            svc = StoryBankService()
            self.story_bank = [
                s.model_dump() if hasattr(s, "model_dump") else {"text": str(s)}
                for s in svc.list_all()
            ]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    # -----------------------------------------------------------------------
    # Networking
    # -----------------------------------------------------------------------

    @rx.event
    async def load_contacts(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.services.networking import NetworkingService

            svc = NetworkingService()
            self.contacts = [c.model_dump() for c in svc.list_all()]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def add_contact(self, name: str, company: str, email: str = "") -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.models.networking import NetworkingContact
            from careerdex.services.networking import NetworkingService

            svc = NetworkingService()
            contact = NetworkingContact(name=name, company=company, email=email)
            svc.add(contact)
            async for _ in self.load_contacts():
                yield
            self.notification = f"Contact added: {name}"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    # -----------------------------------------------------------------------
    # Progress + analytics
    # -----------------------------------------------------------------------

    @rx.event
    async def load_progress(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from careerdex.services.progress import ProgressService

            svc = ProgressService()
            self.progress_data = [s.model_dump() for s in svc.list_snapshots()]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def compute_funnel(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            statuses = [a.get("status", "") for a in self.applications]
            counts: dict[str, int] = {}
            for s in statuses:
                counts[s] = counts.get(s, 0) + 1
            total = len(self.applications)
            self.funnel_data = {
                "total": total,
                "applied": counts.get("applied", 0),
                "responded": counts.get("responded", 0),
                "interview": counts.get("interview", 0),
                "offer": counts.get("offer", 0),
                "accepted": counts.get("accepted", 0),
                "response_rate": round(
                    sum(counts.get(s, 0) for s in ("responded", "interview", "offer", "accepted"))
                    / max(total, 1)
                    * 100,
                    1,
                ),
            }
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    # -----------------------------------------------------------------------
    # Computed vars
    # -----------------------------------------------------------------------

    @rx.var
    def applications_count(self) -> str:
        return str(len(self.applications))

    @rx.var
    def interviews_count(self) -> str:
        return str(sum(1 for a in self.applications if a.get("status") == "interview"))

    @rx.var
    def offers_count(self) -> str:
        return str(sum(1 for a in self.applications if a.get("status") == "offer"))

    @rx.var
    def response_rate(self) -> str:
        total = len(self.applications)
        if total == 0:
            return "0%"
        inactive = ("applied", "saved", "")
        responded = sum(1 for a in self.applications if a.get("status") not in inactive)
        return f"{int(responded / total * 100)}%"

    @rx.var
    def filtered_applications(self) -> list[dict[str, Any]]:
        if not self.search_query:
            return self.applications
        q = self.search_query.lower()
        return [
            a
            for a in self.applications
            if q in a.get("company", "").lower() or q in a.get("role", "").lower()
        ]

    # -----------------------------------------------------------------------
    # Cover Letter
    # -----------------------------------------------------------------------

    @rx.event
    def set_cover_letter_company(self, company: str) -> None:
        self.cover_letter_company = company

    @rx.event
    def set_cover_letter_job_title(self, title: str) -> None:
        self.cover_letter_job_title = title

    @rx.event
    async def generate_cover_letter(self) -> AsyncGenerator[None]:
        if not self.cover_letter_company or not self.cover_letter_job_title:
            self.error = "Company and job title are required"
            return
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.cover_letter import CoverLetterService

            svc = CoverLetterService()
            result = svc.generate(
                company=self.cover_letter_company,
                job_title=self.cover_letter_job_title,
                job_description=self.job_description,
                resume_summary=self.resume_text[:500] if self.resume_text else "",
            )
            self.cover_letter_result = (
                result.model_dump() if hasattr(result, "model_dump") else {"content": str(result)}
            )
            self.notification = "Cover letter generated!"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    async def scan_ats_companies(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.ats_scanner import ATSScanService

            svc = ATSScanService()
            _, all_jobs = svc.scan_all()
            self.scan_results = [j.model_dump() for j in all_jobs]
            self.notification = f"Found {len(all_jobs)} job postings"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def set_research_company(self, name: str) -> None:
        self.research_company_name = name

    @rx.event
    async def do_research(self) -> AsyncGenerator[None]:
        if not self.research_company_name:
            self.error = "Company name is required"
            return
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.company_research import research_company

            result = research_company(self.research_company_name)
            self.research_result = (
                result.model_dump() if hasattr(result, "model_dump") else {"name": str(result)}
            )
            self.notification = "Research complete!"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def set_evaluation_job_desc(self, desc: str) -> None:
        self.evaluation_job_desc = desc

    @rx.event
    async def evaluate_job(self) -> AsyncGenerator[None]:
        if not self.evaluation_job_desc:
            self.error = "Job description is required"
            return
        self.is_loading = True
        self.error = ""
        yield
        try:
            from careerdex.services.job_evaluator import evaluate_job

            result = evaluate_job(self.evaluation_job_desc, self.resume_text)
            self.evaluation_result = (
                result.model_dump() if hasattr(result, "model_dump") else {"grade": str(result)}
            )
            self.notification = "Evaluation complete!"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

    @rx.event
    def set_batch_url(self, url: str) -> None:
        self.batch_url_input = url

    @rx.event
    def set_batch_company(self, company: str) -> None:
        self.batch_company_input = company

    @rx.event
    def set_batch_role(self, role: str) -> None:
        self.batch_role_input = role

    @rx.event
    async def add_batch_job(self) -> None:
        if not self.batch_url_input:
            self.error = "URL is required"
            return
        self.batch_jobs = self.batch_jobs + [
            {
                "url": self.batch_url_input,
                "company": self.batch_company_input,
                "role": self.batch_role_input,
                "status": "pending",
            }
        ]
        self.batch_url_input = ""
        self.batch_company_input = ""
        self.batch_role_input = ""

    @rx.event
    async def clear_batch_jobs(self) -> None:
        self.batch_jobs = []

    @rx.event
    async def apply_batch_jobs(self) -> AsyncGenerator[None]:
        """One-click multi-apply for all pending jobs in batch."""
        self.is_loading = True
        self.error = ""
        yield
        try:
            pending_jobs = [j for j in self.batch_jobs if j.get("status") == "pending"]
            for job in pending_jobs:
                job["status"] = "applying"
            self.batch_jobs = self.batch_jobs.copy()
            yield
            for _i, job in enumerate(pending_jobs):
                try:
                    from careerdex.models.application import ApplicationEntry
                    from careerdex.services.tracker import ApplicationTracker

                    tracker = ApplicationTracker()
                    entry = ApplicationEntry(
                        company=job.get("company", "Unknown"),
                        position=job.get("role", "Unknown Role"),
                        url=job.get("url", ""),
                    )
                    tracker.add(entry)
                    job["status"] = "applied"
                except Exception as e:
                    job["status"] = "failed"
                    job["error"] = str(e)
                self.batch_jobs = self.batch_jobs.copy()
                yield
            applied_count = len([j for j in self.batch_jobs if j.get("status") == "applied"])
            self.notification = f"Applied to {applied_count} jobs!"
            _audit_log(
                "batch_apply",
                details=str(len(self.batch_jobs)),
                status=str(len([j for j in self.batch_jobs if j.get("status") == "applied"])),
            )
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False
