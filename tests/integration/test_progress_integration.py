"""Integration tests — ProgressService: skill snapshots, deltas, persistence."""

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
    s = ProgressService(db_path=tmp_path / "progress.duckdb")
    yield s
    s.close()


def _snapshot(ratings: list[SkillRating] | None = None, **kwargs: object) -> SkillSnapshot:
    if ratings is None:
        ratings = [
            SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=7),
            SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8),
            SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=5),
        ]
    return SkillSnapshot(ratings=ratings, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Snapshot CRUD
# ---------------------------------------------------------------------------


class TestProgressServiceSnapshots:
    def test_add_snapshot_returns_snapshot(self, svc: ProgressService) -> None:
        snap = _snapshot()
        result = svc.add_snapshot(snap)
        assert result.id == snap.id
        assert result.skill_count == 3

    def test_list_snapshots_returns_all(self, svc: ProgressService) -> None:
        svc.add_snapshot(_snapshot())
        svc.add_snapshot(_snapshot())
        snapshots = svc.list_snapshots()
        assert len(snapshots) == 2

    def test_list_snapshots_empty_returns_empty(self, svc: ProgressService) -> None:
        assert svc.list_snapshots() == []

    def test_total_reflects_count(self, svc: ProgressService) -> None:
        assert svc.total() == 0
        svc.add_snapshot(_snapshot())
        svc.add_snapshot(_snapshot())
        assert svc.total() == 2

    def test_delete_snapshot(self, svc: ProgressService) -> None:
        snap = _snapshot()
        svc.add_snapshot(snap)
        assert svc.delete_snapshot(snap.id) is True
        assert svc.total() == 0

    def test_delete_nonexistent_returns_false(self, svc: ProgressService) -> None:
        assert svc.delete_snapshot("nonexistent") is False

    def test_get_latest_returns_most_recent(self, svc: ProgressService) -> None:
        older = _snapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5)],
        )
        newer = _snapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8)],
        )
        svc.add_snapshot(older)
        svc.add_snapshot(newer)
        latest = svc.get_latest()
        assert latest is not None
        assert latest.id == newer.id

    def test_get_latest_empty_returns_none(self, svc: ProgressService) -> None:
        assert svc.get_latest() is None

    def test_get_previous_returns_second_most_recent(self, svc: ProgressService) -> None:
        old = _snapshot(
            date=datetime.now(UTC) - timedelta(days=14),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=4)],
        )
        mid = _snapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=6)],
        )
        new = _snapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(mid)
        svc.add_snapshot(new)
        previous = svc.get_previous()
        assert previous is not None
        assert previous.id == mid.id

    def test_get_previous_with_one_snapshot_returns_none(self, svc: ProgressService) -> None:
        svc.add_snapshot(_snapshot())
        assert svc.get_previous() is None

    def test_notes_preserved(self, svc: ProgressService) -> None:
        snap = _snapshot(notes="Focused on data engineering skills this month")
        svc.add_snapshot(snap)
        latest = svc.get_latest()
        assert latest is not None
        assert latest.notes == "Focused on data engineering skills this month"


# ---------------------------------------------------------------------------
# Skill ratings preserved
# ---------------------------------------------------------------------------


class TestProgressSkillRatings:
    def test_all_ratings_preserved(self, svc: ProgressService) -> None:
        ratings = [
            SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=9),
            SkillRating(skill="AWS", category=SkillCategory.CLOUD, rating=6),
            SkillRating(skill="Kafka", category=SkillCategory.STREAMING, rating=4),
        ]
        snap = SkillSnapshot(ratings=ratings)
        svc.add_snapshot(snap)
        latest = svc.get_latest()
        assert latest is not None
        assert len(latest.ratings) == 3
        skill_map = {r.skill: r.rating for r in latest.ratings}
        assert skill_map["Python"] == 9
        assert skill_map["AWS"] == 6
        assert skill_map["Kafka"] == 4

    def test_rating_categories_preserved(self, svc: ProgressService) -> None:
        ratings = [
            SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8),
        ]
        svc.add_snapshot(SkillSnapshot(ratings=ratings))
        latest = svc.get_latest()
        assert latest is not None
        assert latest.ratings[0].category == SkillCategory.SQL


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


class TestProgressDeltaComputation:
    def test_compute_delta_returns_empty_with_one_snapshot(self, svc: ProgressService) -> None:
        svc.add_snapshot(_snapshot())
        deltas = svc.compute_delta()
        assert deltas == []

    def test_compute_delta_returns_empty_with_no_snapshots(self, svc: ProgressService) -> None:
        assert svc.compute_delta() == []

    def test_compute_delta_improvement(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=14),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert len(deltas) == 1
        assert deltas[0].skill == "Python"
        assert deltas[0].delta == 3
        assert deltas[0].current_rating == 8
        assert deltas[0].previous_rating == 5

    def test_compute_delta_regression(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=9)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=6)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert len(deltas) == 1
        assert deltas[0].delta == -3

    def test_compute_delta_no_change(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7)],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7)],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert len(deltas) == 1
        assert deltas[0].delta == 0

    def test_compute_delta_multiple_skills_ordered_by_abs_delta(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5),
                SkillRating(skill="SQL", category=SkillCategory.SQL, rating=7),
                SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=3),
            ],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=7),  # +2
                SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8),  # +1
                SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=7),  # +4
            ],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        assert len(deltas) == 3
        # sorted by abs(delta) descending — Spark (+4) first
        assert deltas[0].skill == "Spark"
        assert deltas[0].delta == 4

    def test_compute_delta_skill_missing_in_new_not_included(self, svc: ProgressService) -> None:
        old = SkillSnapshot(
            date=datetime.now(UTC) - timedelta(days=7),
            ratings=[
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5),
                SkillRating(skill="Go", category=SkillCategory.OTHER, rating=4),
            ],
        )
        new = SkillSnapshot(
            date=datetime.now(UTC),
            ratings=[
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8),
                # Go missing in new snapshot
            ],
        )
        svc.add_snapshot(old)
        svc.add_snapshot(new)
        deltas = svc.compute_delta()
        skill_names = {d.skill for d in deltas}
        assert "Python" in skill_names
        assert "Go" not in skill_names

    def test_compute_delta_with_explicit_snapshots(self, svc: ProgressService) -> None:
        snap_a = SkillSnapshot(
            ratings=[SkillRating(skill="AWS", category=SkillCategory.CLOUD, rating=3)]
        )
        snap_b = SkillSnapshot(
            ratings=[SkillRating(skill="AWS", category=SkillCategory.CLOUD, rating=9)]
        )
        deltas = svc.compute_delta(current=snap_b, previous=snap_a)
        assert len(deltas) == 1
        assert deltas[0].delta == 6


# ---------------------------------------------------------------------------
# Persistence (DB round-trip)
# ---------------------------------------------------------------------------


class TestProgressPersistence:
    def test_snapshots_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "progress.duckdb"
        s1 = ProgressService(db_path=db)
        snap = _snapshot(notes="Initial assessment")
        s1.add_snapshot(snap)
        s1.close()

        s2 = ProgressService(db_path=db)
        latest = s2.get_latest()
        assert latest is not None
        assert latest.notes == "Initial assessment"
        s2.close()

    def test_multiple_snapshots_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "progress.duckdb"
        s1 = ProgressService(db_path=db)
        for i in range(3):
            s1.add_snapshot(
                SkillSnapshot(
                    date=datetime.now(UTC) - timedelta(days=i * 7),
                    ratings=[
                        SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=5 + i)
                    ],
                )
            )
        s1.close()

        s2 = ProgressService(db_path=db)
        assert s2.total() == 3
        s2.close()

    def test_delta_computed_after_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "progress.duckdb"
        s1 = ProgressService(db_path=db)
        s1.add_snapshot(
            SkillSnapshot(
                date=datetime.now(UTC) - timedelta(days=7),
                ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)],
            )
        )
        s1.add_snapshot(
            SkillSnapshot(
                date=datetime.now(UTC),
                ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=9)],
            )
        )
        s1.close()

        s2 = ProgressService(db_path=db)
        deltas = s2.compute_delta()
        assert len(deltas) == 1
        assert deltas[0].delta == 4
        s2.close()
