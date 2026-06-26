"""Unit tests for Bug 2 — dead letter retry not re-launching the pipeline.

The bug: `scheduler_clear_dead_letter` cleared the DB state (clear_dead_letter
+ clear_run_state) but never re-submitted the pipeline to the jobs thread pool,
so the pipeline stayed stuck forever after an operator cleared the dead letter.

The fix: `scheduler_clear_dead_letter` now calls `run_pipeline_bg(pipeline)`
after the DB cleanup so the pipeline is immediately re-queued.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dex_studio.scheduler import scheduler_clear_dead_letter
from dex_studio.studio_db import StudioDb

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def studio_db(tmp_path: Path) -> StudioDb:
    return StudioDb(tmp_path / "studio.db")


def _make_eng() -> MagicMock:
    eng = MagicMock()
    eng.config_path = None
    return eng


# ── scheduler_clear_dead_letter unit tests ────────────────────────────────────


class TestSchedulerClearDeadLetter:
    """Verify that clearing dead letter state also triggers a background run."""

    def test_run_pipeline_bg_called_with_correct_pipeline_name(self) -> None:
        """The primary regression check: run_pipeline_bg must be called."""
        eng = _make_eng()
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=None),
            patch("dex_studio.jobs.run_pipeline_bg") as mock_run,
        ):
            mock_run.return_value = "started"
            scheduler_clear_dead_letter(eng, "my_pipeline")

        mock_run.assert_called_once_with("my_pipeline")

    def test_run_pipeline_bg_called_even_when_db_is_none(self) -> None:
        """run_pipeline_bg is called unconditionally — not guarded by `if db:`."""
        eng = _make_eng()
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=None),
            patch("dex_studio.jobs.run_pipeline_bg") as mock_run,
        ):
            mock_run.return_value = "started"
            scheduler_clear_dead_letter(eng, "orphan_pipeline")

        mock_run.assert_called_once_with("orphan_pipeline")

    def test_clear_dead_letter_called_on_db(self, studio_db: StudioDb) -> None:
        """db.clear_dead_letter must be called to remove the dead-letter record."""
        eng = _make_eng()
        mock_db = MagicMock(spec=StudioDb)
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=mock_db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started"),
        ):
            scheduler_clear_dead_letter(eng, "etl_pipeline")

        mock_db.clear_dead_letter.assert_called_once_with("etl_pipeline")

    def test_clear_run_state_called_on_db(self, studio_db: StudioDb) -> None:
        """db.clear_run_state must be called to reset retry counters."""
        eng = _make_eng()
        mock_db = MagicMock(spec=StudioDb)
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=mock_db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started"),
        ):
            scheduler_clear_dead_letter(eng, "etl_pipeline")

        mock_db.clear_run_state.assert_called_once_with("etl_pipeline")

    def test_both_db_clears_called_before_run(self) -> None:
        """DB cleanup must happen before the pipeline is re-launched (ordering check)."""
        call_order: list[str] = []

        mock_db = MagicMock(spec=StudioDb)
        mock_db.clear_dead_letter.side_effect = lambda _: call_order.append("clear_dead_letter")
        mock_db.clear_run_state.side_effect = lambda _: call_order.append("clear_run_state")

        eng = _make_eng()
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=mock_db),
            patch("dex_studio.jobs.run_pipeline_bg") as mock_run,
        ):
            mock_run.side_effect = lambda _: call_order.append("run_pipeline_bg")
            mock_run.return_value = "started"
            scheduler_clear_dead_letter(eng, "etl_pipeline")

        assert call_order == ["clear_dead_letter", "clear_run_state", "run_pipeline_bg"], (
            f"Expected DB clears before run, got: {call_order}"
        )

    def test_pipeline_removed_from_dead_letter_in_real_db(self, studio_db: StudioDb) -> None:
        """End-to-end against real StudioDb: dead letter record is gone after clear."""
        # Seed a dead letter entry
        studio_db.record_dead_letter("stuck_pipe", "timeout error", attempts=3)
        studio_db.mark_dead("stuck_pipe")

        dead_before = studio_db.get_dead_letter()
        assert any(d["pipeline"] == "stuck_pipe" for d in dead_before), (
            "precondition: dead letter entry should exist"
        )

        eng = _make_eng()
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=studio_db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started") as mock_run,
        ):
            scheduler_clear_dead_letter(eng, "stuck_pipe")

        dead_after = studio_db.get_dead_letter()
        assert not any(d["pipeline"] == "stuck_pipe" for d in dead_after), (
            "dead letter record should be removed after clear"
        )
        mock_run.assert_called_once_with("stuck_pipe")

    def test_run_state_cleared_in_real_db(self, studio_db: StudioDb) -> None:
        """End-to-end against real StudioDb: run state (retry counter) is reset."""
        from datetime import UTC, datetime, timedelta

        retry_at = datetime.now(UTC) + timedelta(seconds=60)
        studio_db.increment_attempts("stuck_pipe", retry_at)

        state_before = studio_db.get_run_state("stuck_pipe")
        assert state_before["attempts"] >= 1, "precondition: attempt counter should be set"

        eng = _make_eng()
        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=studio_db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started"),
        ):
            scheduler_clear_dead_letter(eng, "stuck_pipe")

        state_after = studio_db.get_run_state("stuck_pipe")
        assert state_after["attempts"] == 0, "run state attempts should be reset to 0 after clear"

    def test_different_pipeline_names_forwarded_correctly(self) -> None:
        """run_pipeline_bg receives exactly the pipeline name passed to
        scheduler_clear_dead_letter."""
        eng = _make_eng()
        for pipeline_name in ("ingest_movies", "transform_ratings", "export_gold"):
            with (
                patch("dex_studio.scheduler._get_or_create_studio_db", return_value=None),
                patch("dex_studio.jobs.run_pipeline_bg") as mock_run,
            ):
                mock_run.return_value = "started"
                scheduler_clear_dead_letter(eng, pipeline_name)
            mock_run.assert_called_once_with(pipeline_name)
