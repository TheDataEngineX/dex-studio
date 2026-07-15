from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dex_studio.scheduler import SchedulerConfig, _build_dag, _run_due_pipelines, resolve_depends_on
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
    # Real eng.config.project.name (see app.py) — set explicitly so
    # MagicMock doesn't auto-vivify a non-None child mock in its place,
    # which would defeat resolve_depends_on's getattr(..., "default") fallback.
    eng.config.project = SimpleNamespace(name="default")
    return eng


_EPOCH = datetime(2020, 1, 1, tzinfo=UTC)


def test_no_pipelines_runs_nothing(studio_db: StudioDb) -> None:
    eng = _make_eng({})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)
    assert ran == []


def test_pipeline_with_no_schedule_skipped(studio_db: StudioDb) -> None:
    eng = _make_eng({"p": _PipeCfg(schedule="")})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)
    assert ran == []


def test_pipeline_already_locked_skipped(studio_db: StudioDb) -> None:
    studio_db.acquire_lock("p")
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *")})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)
    assert ran == []


def test_never_run_pipeline_waits_for_next_tick_not_immediate(studio_db: StudioDb) -> None:
    """A pipeline with no run history must NOT fire the instant the scheduler
    boots (e.g. every app restart) — it should wait for its next natural cron
    tick, same as a pipeline that has already run once."""
    eng = _make_eng({"p": _PipeCfg(schedule="0 3 * * *")})  # daily at 03:00
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []
    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)
    assert ran == []


def test_running_row_with_no_lock_is_reconciled(studio_db: StudioDb) -> None:
    """A crashed process (e.g. OOM-killed) can leave a 'running' row behind
    with no corresponding lock — the lock itself doesn't survive process
    death, but nothing else marks the run as failed. A tick must catch this
    immediately rather than waiting out the full stale-lock timeout.
    """
    run_id = studio_db.start_run("orphan", triggered_by="scheduler")
    assert studio_db.locked_pipelines() == []

    eng = _make_eng({})
    cfg = SchedulerConfig(enabled=True)
    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=lambda _: None)

    runs = studio_db.get_runs("orphan", limit=1)
    assert runs[0]["id"] == run_id
    assert runs[0]["status"] == "failed"
    assert runs[0]["finished_at"]


def test_hard_kill_still_persists_retry_state(studio_db: StudioDb) -> None:
    """A SIGKILL (e.g. OOM) never reaches `except Exception` — simulate it
    with SystemExit, which `except Exception` cannot catch either. Attempt
    state must already be persisted before the pipeline runs, otherwise a
    real hard kill leaves no record and the next scheduler tick refires the
    same pipeline immediately with no backoff, forever."""
    studio_db.set_last_run("p", datetime(2019, 12, 31, 23, 58, tzinfo=UTC))
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *")})
    # Mock the job queue to avoid real engine
    from unittest.mock import patch
    with patch("dex_studio.jobs.run_pipeline_bg") as mock_run_bg:
        mock_run_bg.return_value = "queued"
        cfg = SchedulerConfig(enabled=True)
        ran: list[str] = []
        _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)
        mock_run_bg.assert_called_once_with("p", triggered_by="scheduler")


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
    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)

    eng.run_pipeline.assert_not_called()
    state = studio_db.get_run_state("p")
    assert state["state"] == "dead"


def test_depends_on_prefers_db_model_over_yaml(studio_db: StudioDb) -> None:
    from dex_studio.pipeline_definition import PipelineDefinitionStore

    store = PipelineDefinitionStore(studio_db)
    store.import_from_yaml_steps(
        project_id="default",
        pipeline_name="p",
        source="src",
        destination="dst",
        schedule="* * * * *",
        depends_on=["db_dependency"],
        steps=[],
    )

    # YAML config disagrees with the DB — DB should win once a row exists.
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *", depends_on=["yaml_dependency"])})

    resolved = resolve_depends_on(eng, studio_db, "p")

    assert resolved == ["db_dependency"]


def test_depends_on_falls_back_to_yaml_when_unmigrated(studio_db: StudioDb) -> None:
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *", depends_on=["yaml_dependency"])})

    resolved = resolve_depends_on(eng, studio_db, "p")

    assert resolved == ["yaml_dependency"]


def test_depends_on_falls_back_to_yaml_on_db_race(
    studio_db: StudioDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent edit (e.g. via the Studio UI) can delete/corrupt the
    pipeline_defs row between reads. resolve_depends_on must fall back to
    YAML instead of letting an exception (or an old bare assert) escape and
    abort DAG construction for the whole scheduler tick."""

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated concurrent row deletion")

    monkeypatch.setattr(studio_db, "get_pipeline_def", _raise)

    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *", depends_on=["yaml_dependency"])})

    resolved = resolve_depends_on(eng, studio_db, "p")

    assert resolved == ["yaml_dependency"]


def test_build_dag_uses_db_model_over_yaml(studio_db: StudioDb) -> None:
    """The DAG used for execution order must reflect the same DB-preferred
    source as resolve_depends_on, not the raw YAML depends_on build_dag()
    (from dataenginex) would have read."""
    from dex_studio.pipeline_definition import PipelineDefinitionStore

    store = PipelineDefinitionStore(studio_db)
    store.import_from_yaml_steps(
        project_id="default",
        pipeline_name="p",
        source="src",
        destination="dst",
        schedule="* * * * *",
        depends_on=["db_dependency"],
        steps=[],
    )

    # YAML says "p" is a root (no depends_on) — DB model disagrees.
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *", depends_on=[])})

    dag = _build_dag(eng, studio_db, eng.config.data.pipelines)

    assert dag == {"p": ["db_dependency"]}


def test_migrated_dependent_does_not_fire_as_root(studio_db: StudioDb) -> None:
    """A pipeline that YAML lists as a root (no depends_on) but whose DB
    model gives it a dependency must not fire on its own cron schedule —
    the execution DAG has to match the DB model, not the stale YAML one."""
    from dex_studio.pipeline_definition import PipelineDefinitionStore

    store = PipelineDefinitionStore(studio_db)
    store.import_from_yaml_steps(
        project_id="default",
        pipeline_name="p",
        source="src",
        destination="dst",
        schedule="* * * * *",
        depends_on=["upstream"],
        steps=[],
    )

    # YAML config still shows "p" as a root pipeline (no depends_on).
    eng = _make_eng({"p": _PipeCfg(schedule="* * * * *", depends_on=[])})
    cfg = SchedulerConfig(enabled=True)
    ran: list[str] = []

    _run_due_pipelines(eng, cfg, studio_db, now=_EPOCH, ran_cb=ran.append)

    eng.run_pipeline.assert_not_called()
    assert ran == []
