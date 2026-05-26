"""Batch runner - orchestrates parallel job processing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

import structlog

from careerdex.services.batch_state import (
    BatchJob,
    BatchState,
    JobStatus,
    load_state,
    save_state,
)

logger = structlog.get_logger()

__all__ = ["BatchRunner", "run_batch"]


class BatchRunner:
    """Orchestrate batch processing of job evaluations."""

    def __init__(self, state: BatchState | None = None, max_concurrent: int = 3):
        self.state = state or BatchState()
        self.max_concurrent = max_concurrent
        self._running = False

    async def process_job(self, job: BatchJob) -> BatchJob:
        """Process a single job."""
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now()

        try:
            job_desc = f"Job at {job.company}: {job.role}"

            from careerdex.services.job_evaluator import evaluate_job

            result = evaluate_job(job_desc)

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now()
            job.score = result.overall_score
            job.grade = result.overall_grade
            job.report_path = f"reports/{job.id}-{job.company}.md"

            logger.info("Job completed", job_id=job.id, score=job.score, grade=job.grade)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            job.error = str(e)
            job.retries += 1

            logger.error("Job failed", job_id=job.id, error=str(e))

        return job

    async def run(
        self,
        urls: list[str],
        on_progress: Callable[..., Any] | None = None,
    ) -> BatchState:
        """Run batch processing on list of URLs."""
        self._running = False

        self.state.add_jobs(urls)

        pending_jobs = self.state.get_pending()

        logger.info("Starting batch", total=len(pending_jobs))

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_with_semaphore(job: BatchJob) -> None:
            async with semaphore:
                if self._running:
                    await self.process_job(job)
                    save_state(self.state)
                    if on_progress:
                        on_progress(self.state.get_stats())

        tasks = [process_with_semaphore(job) for job in pending_jobs]
        await asyncio.gather(*tasks, return_exceptions=True)

        self._running = False
        save_state(self.state)

        logger.info("Batch complete", stats=self.state.get_stats())

        return self.state

    def retry_failed(self) -> list[BatchJob]:
        """Retry failed jobs."""
        failed = self.state.get_failed()
        for job in failed:
            job.status = JobStatus.PENDING
            job.retries += 1
        save_state(self.state)
        return failed

    def cancel(self) -> None:
        """Cancel running batch."""
        self._running = False


async def run_batch(
    urls: list[str],
    max_concurrent: int = 3,
    on_progress: Callable[..., Any] | None = None,
) -> BatchState:
    """Convenience function to run batch."""
    state = load_state()
    runner = BatchRunner(state, max_concurrent)
    return await runner.run(urls, on_progress)
