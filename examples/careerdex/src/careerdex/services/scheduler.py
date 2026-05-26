"""ScheduleManager — cron-based job aggregation scheduling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
from pydantic import BaseModel

from careerdex.models.job import JobSource

if TYPE_CHECKING:
    import structlog

import structlog

logger = structlog.get_logger()

__all__ = ["ScheduleManager", "ScheduledJob"]


class ScheduledJob(BaseModel):
    """A scheduled job aggregation."""

    job_source: JobSource
    cron_expr: str
    last_run: datetime | None = None
    next_run: datetime | None = None
    is_active: bool = True


class ScheduleManager:
    """ScheduleManager manages cron-based job aggregation scheduling.

    Usage:
        mgr = ScheduleManager()
        mgr.schedule_aggregation(JobSource.LINKEDIN, "0 */6 * * *")
        mgr.start()  # Start background scheduler
        mgr.close()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path.home() / ".careerdex" / "schedules.duckdb"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._scheduler: Any | None = None
        self._job_service: Any = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                job_source TEXT PRIMARY KEY,
                cron_expr TEXT NOT NULL,
                last_run TIMESTAMP,
                next_run TIMESTAMP,
                is_active BOOL DEFAULT true
            )
        """)

    def schedule_aggregation(self, job_source: JobSource, cron_expr: str) -> None:
        """Schedule a job source for periodic aggregation."""
        import pytz

        self._conn.execute(
            """
            INSERT INTO schedules (job_source, cron_expr, next_run, is_active)
            VALUES (?, ?, ?, true)
            ON CONFLICT (job_source) DO UPDATE SET
                cron_expr = excluded.cron_expr,
                next_run = excluded.next_run
            """,
            [job_source.value, cron_expr, datetime.now(pytz.UTC)],
        )
        self._conn.commit()
        self._restart_scheduler()
        logger.info("scheduled_aggregation", source=job_source, cron=cron_expr)

    def unschedule_aggregation(self, job_source: JobSource) -> None:
        """Remove a scheduled job source."""
        self._conn.execute(
            "DELETE FROM schedules WHERE job_source = ?",
            [job_source.value],
        )
        self._conn.commit()
        self._restart_scheduler()
        logger.info("unscheduled_aggregation", source=job_source)

    def list_scheduled(self) -> list[ScheduledJob]:
        """List all scheduled jobs."""
        rows = self._conn.execute(
            "SELECT job_source, cron_expr, last_run, next_run, is_active FROM schedules"
        ).fetchall()
        return [
            ScheduledJob(
                job_source=JobSource(row[0]),
                cron_expr=row[1],
                last_run=row[2],
                next_run=row[3],
                is_active=row[4],
            )
            for row in rows
        ]

    def start(self) -> None:
        """Start the background scheduler thread."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._scheduler = BackgroundScheduler()
            for sched in self.list_scheduled():
                if sched.is_active:
                    self._add_cron_job(sched)
            self._scheduler.start()
            logger.info("scheduler_started")
        except Exception:
            logger.warning("apscheduler_not_available")

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self._scheduler:
            self._scheduler.shutdown()
            self._scheduler = None

    def _restart_scheduler(self) -> None:
        """Restart the scheduler to pick up schedule changes."""
        self.stop()
        if self._scheduler or not self._scheduler:
            self.start()

    def _add_cron_job(self, sched: ScheduledJob) -> None:
        """Add a cron job to the background scheduler."""
        if self._scheduler is None:
            return
        try:
            from apscheduler.triggers.cron import CronTrigger

            trigger = CronTrigger.from_crontab(sched.cron_expr)
            self._scheduler.add_job(
                self._run_aggregation,
                trigger=trigger,
                args=[sched.job_source],
                id=sched.job_source.value,
                replace_existing=True,
            )
        except Exception:
            logger.warning("cron_trigger_failed", source=sched.job_source)

    def _run_aggregation(self, job_source: JobSource) -> None:
        """Run the aggregation for a job source."""
        import pytz

        if self._job_service is None:
            try:
                from careerdex.services.search import JobService

                self._job_service = JobService()
            except Exception:
                return
        try:
            import asyncio

            count = asyncio.run(self._job_service.refresh_source(job_source.value, 50))
            self._conn.execute(
                "UPDATE schedules SET last_run = ?, next_run = ? WHERE job_source = ?",
                [datetime.now(pytz.UTC), datetime.now(pytz.UTC), job_source.value],
            )
            self._conn.commit()
            logger.info("aggregation_completed", source=job_source, count=count)
        except Exception:
            logger.warning("aggregation_failed", source=job_source)

    async def run_now(self, job_source: JobSource, job_service: Any) -> int:
        """Run aggregation immediately for a job source."""
        self._job_service = job_service
        result: int = await job_service.refresh_source(job_source.value, 50)
        return result

    def close(self) -> None:
        """Close the scheduler and database connection."""
        self.stop()
        self._conn.close()
