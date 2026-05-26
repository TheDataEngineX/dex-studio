"""Batch state management - tracks batch job progress."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["BatchJob", "BatchState", "load_state", "save_state"]


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BatchJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    url: str
    company: str = ""
    role: str = ""
    status: JobStatus = JobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    score: float | None = None
    grade: str | None = None
    report_path: str | None = None
    pdf_path: str | None = None
    error: str | None = None
    retries: int = 0


class BatchState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    jobs: list[BatchJob] = Field(default_factory=list)

    def add_job(self, url: str, company: str = "", role: str = "") -> BatchJob:
        """Add a new job to the batch."""
        job = BatchJob(url=url, company=company, role=role)
        self.jobs.append(job)
        return job

    def add_jobs(self, urls: list[str]) -> list[BatchJob]:
        """Add multiple jobs from URLs."""
        jobs = []
        for url in urls:
            url = url.strip()
            if url and url.startswith("http"):
                job = self.add_job(url)
                jobs.append(job)
        return jobs

    def get_pending(self) -> list[BatchJob]:
        """Get all pending jobs."""
        return [j for j in self.jobs if j.status == JobStatus.PENDING]

    def get_failed(self) -> list[BatchJob]:
        """Get all failed jobs that can be retried."""
        return [j for j in self.jobs if j.status == JobStatus.FAILED and j.retries < 3]

    def get_stats(self) -> dict[str, int]:
        """Get batch statistics."""
        return {
            "total": len(self.jobs),
            "pending": len([j for j in self.jobs if j.status == JobStatus.PENDING]),
            "processing": len([j for j in self.jobs if j.status == JobStatus.PROCESSING]),
            "completed": len([j for j in self.jobs if j.status == JobStatus.COMPLETED]),
            "failed": len([j for j in self.jobs if j.status == JobStatus.FAILED]),
        }

    def update_job(self, job_id: str, **updates: Any) -> None:
        """Update a job's status and details."""
        for job in self.jobs:
            if job.id == job_id:
                for key, value in updates.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                break


def get_state_path() -> Path:
    """Get the default state file path."""
    state_dir = Path.home() / ".dex-studio" / "careerdex" / "batch"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "batch_state.json"


def load_state(path: Path | None = None) -> BatchState:
    """Load batch state from file."""
    path = path or get_state_path()
    if path.exists():
        import json

        data = json.loads(path.read_text())
        return BatchState(**data)
    return BatchState()


def save_state(state: BatchState, path: Path | None = None) -> None:
    """Save batch state to file."""
    path = path or get_state_path()
    import json

    path.write_text(json.dumps(state.model_dump(), indent=2, default=str))
