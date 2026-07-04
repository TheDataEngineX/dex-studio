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


def test_hard_kill_still_persists_retry_state(studio_db: StudioDb) -> None:
    """A SIGKILL (e.g. OOM) never reaches `except Exception` — simulate it
    with SystemExit, which `except Exception` cannot catch either. Attempt
    state must already be persisted before the pipeline runs, otherwise a
    real hard kill leaves no record and the next scheduler tick refires the
    same pipeline immediately with no backoff, forever."""
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *")})
    eng.run_pipeline.side_effect = SystemExit(1)
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    with pytest.raises(SystemExit):
        _run_due_pipelines(eng, cfg, studio_db, epoch=_EPOCH, ran_cb=ran.append)

    state = studio_db.get_run_state("p")
    assert state["attempts"] == 1
    assert state["state"] == "retrying"


def test_hard_kill_exhausted_attempts_dead_letters_without_running(studio_db: StudioDb) -> None:
    """If prior hard kills already burned the attempt budget (attempts ==
    retry_attempts, all via the pre-run guard — never touching the except
    block), the next tick must dead-letter without calling run_pipeline
    again, not keep retrying forever with backoff."""
    cfg = SchedulerConfig(enabled=True)
    past = datetime(2019, 1, 1, tzinfo=UTC)
    for _ in range(cfg.retry_attempts):
        studio_db.increment_attempts("p", past)

    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *")})
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, epoch=_EPOCH, ran_cb=ran.append)

    eng.run_pipeline.assert_not_called()
    state = studio_db.get_run_state("p")
    assert state["state"] == "dead"
