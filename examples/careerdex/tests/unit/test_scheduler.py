"""Tests for ScheduleManager — cron-based job aggregation scheduling."""

from __future__ import annotations

from pathlib import Path

import pytest

from careerdex.models.job import JobSource
from careerdex.services.scheduler import ScheduleManager


@pytest.fixture
def scheduler(tmp_path: Path) -> ScheduleManager:
    """Fresh scheduler backed by a temp DuckDB file — isolated per test."""
    s = ScheduleManager(db_path=tmp_path / "test_schedules.duckdb")
    yield s
    s.close()


class TestScheduleAggregation:
    def test_schedule_aggregation_adds_cron_job(self, scheduler: ScheduleManager) -> None:
        scheduler.schedule_aggregation(JobSource.LINKEDIN, "0 */6 * * *")
        scheduled = scheduler.list_scheduled()
        assert len(scheduled) == 1
        assert scheduled[0].job_source == JobSource.LINKEDIN
        assert scheduled[0].cron_expr == "0 */6 * * *"

    def test_schedule_aggregation_updates_existing(self, scheduler: ScheduleManager) -> None:
        scheduler.schedule_aggregation(JobSource.LINKEDIN, "0 */6 * * *")
        scheduler.schedule_aggregation(JobSource.LINKEDIN, "0 */4 * * *")
        scheduled = scheduler.list_scheduled()
        assert len(scheduled) == 1
        assert scheduled[0].cron_expr == "0 */4 * * *"


class TestUnscheduleAggregation:
    def test_unschedule_removes_scheduled_job(self, scheduler: ScheduleManager) -> None:
        scheduler.schedule_aggregation(JobSource.LINKEDIN, "0 */6 * * *")
        scheduler.unschedule_aggregation(JobSource.LINKEDIN)
        scheduled = scheduler.list_scheduled()
        assert len(scheduled) == 0


class TestListScheduled:
    def test_list_scheduled_returns_all(self, scheduler: ScheduleManager) -> None:
        scheduler.schedule_aggregation(JobSource.LINKEDIN, "0 */6 * * *")
        scheduler.schedule_aggregation(JobSource.GREENHOUSE, "0 */12 * * *")
        scheduled = scheduler.list_scheduled()
        assert len(scheduled) == 2
        sources = {s.job_source for s in scheduled}
        assert sources == {JobSource.LINKEDIN, JobSource.GREENHOUSE}

    def test_list_scheduled_returns_empty_when_none(self, scheduler: ScheduleManager) -> None:
        scheduled = scheduler.list_scheduled()
        assert len(scheduled) == 0


class TestRunNow:
    @pytest.mark.asyncio
    async def test_run_now_triggers_refresh(self, scheduler: ScheduleManager) -> None:
        from careerdex.services.search import JobService

        svc = JobService()
        count = await scheduler.run_now(JobSource.LINKEDIN, svc)
        assert count >= 0
        svc.close()
