from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dex_studio.scheduler import SchedulerConfig, _run_due_pipelines
from dex_studio.studio_db import StudioDb


@pytest.fixture
def studio_db(tmp_path: Path) -> StudioDb:
    return StudioDb(tmp_path / "studio.db")


class _PipeCfg:
    def __init__(self, schedule: str = "0 3 * * *", depends_on: list[str] | None = None):
        self.schedule = schedule
        self.depends_on = depends_on or []


def _make_eng(pipelines: dict) -> MagicMock:
    eng = MagicMock()
    eng.config_path = None
    eng.config.data.pipelines = pipelines
    return eng


_EPOCH = datetime(2020, 1, 1, tzinfo=UTC)


def test_no_pipelines_runs_nothing(studio_db: StudioDb) -> None:
    eng = _make_eng({})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, epoch=_EPOCH, ran_cb=ran.append)
    assert ran == []


def test_pipeline_with_no_schedule_skipped(studio_db: StudioDb) -> None:
    eng = _make_eng({"p": _PipeCfg(schedule="")})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, epoch=_EPOCH, ran_cb=ran.append)
    assert ran == []


def test_pipeline_already_locked_skipped(studio_db: StudioDb) -> None:
    studio_db.acquire_lock("p")
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *")})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, epoch=_EPOCH, ran_cb=ran.append)
    assert ran == []
