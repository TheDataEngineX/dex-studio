"""Regression tests — dead letter retry (Bug 2 fix).

Before fix: scheduler_clear_dead_letter only cleared DB records but did not
trigger a re-run. User had to click a separate "Retry" button.

After fix: scheduler_clear_dead_letter clears the dead letter + run state AND
immediately calls run_pipeline_bg(pipeline) to start a new run.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestSchedulerClearDeadLetter:
    def _make_db(self) -> MagicMock:
        db = MagicMock()
        return db

    def test_calls_clear_dead_letter(self) -> None:
        eng = MagicMock()
        db = self._make_db()

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started"),
        ):
            from dex_studio.scheduler import scheduler_clear_dead_letter

            scheduler_clear_dead_letter(eng, "my_pipeline")

        db.clear_dead_letter.assert_called_once_with("my_pipeline")

    def test_calls_clear_run_state(self) -> None:
        eng = MagicMock()
        db = self._make_db()

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started"),
        ):
            from dex_studio.scheduler import scheduler_clear_dead_letter

            scheduler_clear_dead_letter(eng, "my_pipeline")

        db.clear_run_state.assert_called_once_with("my_pipeline")

    def test_triggers_immediate_run(self) -> None:
        """Core regression: after clearing, pipeline must be re-triggered."""
        eng = MagicMock()
        db = self._make_db()

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started") as mock_run,
        ):
            from dex_studio.scheduler import scheduler_clear_dead_letter

            scheduler_clear_dead_letter(eng, "my_pipeline")

        mock_run.assert_called_once_with("my_pipeline")

    def test_order_clear_before_run(self) -> None:
        """DB must be cleared before triggering, so state is not 'dead' when run starts."""
        eng = MagicMock()
        db = self._make_db()
        call_order: list[str] = []

        db.clear_dead_letter.side_effect = lambda _: call_order.append("clear_dead_letter")
        db.clear_run_state.side_effect = lambda _: call_order.append("clear_run_state")

        def mock_run(name: str) -> str:
            call_order.append("run_pipeline_bg")
            return "started"

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=db),
            patch("dex_studio.jobs.run_pipeline_bg", side_effect=mock_run),
        ):
            from dex_studio.scheduler import scheduler_clear_dead_letter

            scheduler_clear_dead_letter(eng, "my_pipeline")

        assert call_order.index("run_pipeline_bg") > call_order.index("clear_run_state"), (
            "run_pipeline_bg must be called AFTER clear_run_state "
            "so state is not 'dead' when run starts"
        )

    def test_run_triggered_even_when_db_none(self) -> None:
        """run_pipeline_bg fires even if no StudioDb is available."""
        eng = MagicMock()

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=None),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started") as mock_run,
        ):
            from dex_studio.scheduler import scheduler_clear_dead_letter

            scheduler_clear_dead_letter(eng, "orphan_pipeline")

        mock_run.assert_called_once_with("orphan_pipeline")

    def test_correct_pipeline_name_passed(self) -> None:
        eng = MagicMock()
        db = self._make_db()

        with (
            patch("dex_studio.scheduler._get_or_create_studio_db", return_value=db),
            patch("dex_studio.jobs.run_pipeline_bg", return_value="started") as mock_run,
        ):
            from dex_studio.scheduler import scheduler_clear_dead_letter

            scheduler_clear_dead_letter(eng, "specific_pipeline_name")

        db.clear_dead_letter.assert_called_with("specific_pipeline_name")
        db.clear_run_state.assert_called_with("specific_pipeline_name")
        mock_run.assert_called_with("specific_pipeline_name")
