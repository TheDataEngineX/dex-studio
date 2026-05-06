"""Unit tests for ProgressService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from careerdex.models.progress import (
    SkillCategory,
    SkillRating,
    SkillSnapshot,
)
from careerdex.services.progress import ProgressService


@pytest.fixture()
def svc(tmp_path: Path) -> ProgressService:
    return ProgressService(db_path=tmp_path / "progress.duckdb")


def _snap(*skills: tuple[str, SkillCategory, int]) -> SkillSnapshot:
    """Build a snapshot from (name, category, rating) tuples."""
    return SkillSnapshot(ratings=[SkillRating(skill=n, category=c, rating=r) for n, c, r in skills])


class TestAddGetLatest:
    def test_round_trip(self, svc: ProgressService) -> None:
        snap = _snap(("Spark", SkillCategory.DATA_ENGINEERING, 7))
        svc.add_snapshot(snap)
        latest = svc.get_latest()
        assert latest is not None
        assert latest.id == snap.id
        assert latest.ratings[0].skill == "Spark"
        assert latest.ratings[0].rating == 7

    def test_get_latest_empty(self, svc: ProgressService) -> None:
        assert svc.get_latest() is None

    def test_latest_is_newest(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        latest = svc.get_latest()
        assert latest is not None
        assert latest.id == new.id


class TestGetPrevious:
    def test_none_with_one_snapshot(self, svc: ProgressService) -> None:
        svc.add_snapshot(_snap(("SQL", SkillCategory.SQL, 5)))
        assert svc.get_previous() is None

    def test_returns_second_most_recent(self, svc: ProgressService) -> None:
        snap1 = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
        )
        snap2 = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8)],
        )
        svc.add_snapshot(snap1)
        svc.add_snapshot(snap2)
        prev = svc.get_previous()
        assert prev is not None
        assert prev.id == snap1.id


class TestListSnapshots:
    def test_empty(self, svc: ProgressService) -> None:
        assert svc.list_snapshots() == []

    def test_newest_first(self, svc: ProgressService) -> None:
        old = SkillSnapshot(date=datetime.now(UTC) - timedelta(days=10))
        new = SkillSnapshot(date=datetime.now(UTC))
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        snaps = svc.list_snapshots()
        assert snaps[0].id == new.id
        assert snaps[1].id == old.id


class TestDelete:
    def test_returns_true_then_false(self, svc: ProgressService) -> None:
        snap = _snap(("Python", SkillCategory.PYTHON, 6))
        svc.add_snapshot(snap)
        assert svc.delete_snapshot(snap.id) is True
        assert svc.delete_snapshot(snap.id) is False

    def test_removes_from_db(self, svc: ProgressService) -> None:
        snap = _snap(("Python", SkillCategory.PYTHON, 6))
        svc.add_snapshot(snap)
        svc.delete_snapshot(snap.id)
        assert svc.get_latest() is None


class TestTotal:
    def test_empty(self, svc: ProgressService) -> None:
        assert svc.total() == 0

    def test_counts_correctly(self, svc: ProgressService) -> None:
        svc.add_snapshot(_snap(("SQL", SkillCategory.SQL, 5)))
        svc.add_snapshot(_snap(("Python", SkillCategory.PYTHON, 7)))
        assert svc.total() == 2


class TestComputeDelta:
    def test_empty_returns_empty_list(self, svc: ProgressService) -> None:
        assert svc.compute_delta() == []

    def test_single_snapshot_returns_empty(self, svc: ProgressService) -> None:
        svc.add_snapshot(_snap(("SQL", SkillCategory.SQL, 5)))
        assert svc.compute_delta() == []

    def test_up_trend(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert len(deltas) == 1
        assert deltas[0].trend == "up"
        assert deltas[0].delta == 3

    def test_down_trend(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert deltas[0].trend == "down"
        assert deltas[0].delta == -3

    def test_same_trend(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert deltas[0].trend == "same"
        assert deltas[0].delta == 0

    def test_skill_only_in_one_snapshot_excluded(self, svc: ProgressService) -> None:
        """Skills not in both snapshots are silently dropped — no crash."""
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[
                SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7),
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8),
            ],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        skill_names = {d.skill for d in deltas}
        assert "SQL" in skill_names
        assert "Python" not in skill_names  # only in new, not in old


class TestClose:
    def test_close_does_not_raise(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        svc.close()


class TestGenerateImprovementPlan:
    def test_raises_runtime_error_when_no_snapshot(self, svc: ProgressService) -> None:
        import unittest.mock

        import httpx
        import pytest

        err = httpx.ConnectError("down")
        with (
            unittest.mock.patch("httpx.post", side_effect=err),
            pytest.raises(RuntimeError),
        ):
            svc.suggest_improvements()

    def test_raises_when_ollama_unavailable(self, svc: ProgressService) -> None:
        import unittest.mock

        import httpx
        import pytest

        snapshot = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8)],
        )
        svc.add_snapshot(snapshot)

        err = httpx.ConnectError("down")
        with (
            unittest.mock.patch("httpx.post", side_effect=err),
            pytest.raises(RuntimeError, match="Ollama"),
        ):
            svc.suggest_improvements()

    def test_generate_plan_success(self, svc: ProgressService) -> None:
        import json
        import unittest.mock

        snapshot = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=7)],
        )
        svc.add_snapshot(snapshot)

        plan = {
            "focus_areas": ["Python advanced patterns"],
            "weekly_goals": ["Complete one project"],
            "resources": [{"title": "Book", "url": "https://example.com", "type": "book"}],
            "timeline": "4 weeks",
            "summary": "Focus on Python.",
        }
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(plan)}
        mock_resp.raise_for_status.return_value = None

        with unittest.mock.patch("httpx.post", return_value=mock_resp):
            result = svc.suggest_improvements()

        assert "focus_areas" in result

    def test_generate_plan_with_deltas(self, svc: ProgressService) -> None:
        import json
        import unittest.mock

        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=30),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)

        deltas = svc.compute_delta()
        plan_data = {
            "focus_areas": [],
            "weekly_goals": [],
            "resources": [],
            "timeline": "",
            "summary": "ok",
        }
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(plan_data)}
        mock_resp.raise_for_status.return_value = None

        with unittest.mock.patch("httpx.post", return_value=mock_resp):
            result = svc.suggest_improvements(deltas=deltas)

        assert isinstance(result, dict)


class TestProgressEdgeCases:
    def test_all_skill_categories(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        for cat in SkillCategory:
            snap = SkillSnapshot(ratings=[SkillRating(skill="Test", category=cat, rating=5)])
            svc.add_snapshot(snap)
        assert svc.total() == len(SkillCategory)

    def test_rating_bounds(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        snap = SkillSnapshot(
            ratings=[SkillRating(skill="Test", category=SkillCategory.PYTHON, rating=1)]
        )
        svc.add_snapshot(snap)
        result = svc.get_latest()
        assert result is not None
        assert result.ratings[0].rating == 1

    def test_rating_max(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        snap = SkillSnapshot(
            ratings=[SkillRating(skill="Test", category=SkillCategory.PYTHON, rating=10)]
        )
        svc.add_snapshot(snap)
        result = svc.get_latest()
        assert result is not None
        assert result.ratings[0].rating == 10

    def test_multiple_skills_in_snapshot(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        snap = SkillSnapshot(
            ratings=[
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8),
                SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7),
                SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=6),
            ]
        )
        svc.add_snapshot(snap)
        result = svc.get_latest()
        assert result is not None
        assert len(result.ratings) == 3

    def test_empty_ratings_handled(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        snap = SkillSnapshot(ratings=[])
        svc.add_snapshot(snap)
        result = svc.get_latest()
        assert result is not None
        assert result.ratings == []

    def test_delta_with_no_change(self, tmp_path: Path) -> None:
        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert len(deltas) == 1
        assert deltas[0].delta == 0
        assert deltas[0].trend == "same"
