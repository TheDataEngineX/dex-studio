"""Unit tests for progress domain models (pure, no I/O)."""

from __future__ import annotations

import pytest
from careerdex.models.progress import (
    SkillCategory,
    SkillDelta,
    SkillRating,
    SkillSnapshot,
)


class TestSkillRatingClamp:
    def test_clamps_below_min(self) -> None:
        r = SkillRating(skill="SQL", category=SkillCategory.SQL, rating=0)
        assert r.rating == 1

    def test_clamps_above_max(self) -> None:
        r = SkillRating(skill="SQL", category=SkillCategory.SQL, rating=11)
        assert r.rating == 10

    def test_valid_mid_value_unchanged(self) -> None:
        r = SkillRating(skill="SQL", category=SkillCategory.SQL, rating=5)
        assert r.rating == 5

    def test_boundary_min(self) -> None:
        r = SkillRating(skill="SQL", category=SkillCategory.SQL, rating=1)
        assert r.rating == 1

    def test_boundary_max(self) -> None:
        r = SkillRating(skill="SQL", category=SkillCategory.SQL, rating=10)
        assert r.rating == 10


class TestSkillSnapshotAverageRating:
    def test_empty_returns_zero(self) -> None:
        snap = SkillSnapshot(ratings=[])
        assert snap.average_rating == pytest.approx(0.0)

    def test_single_skill(self) -> None:
        snap = SkillSnapshot(
            ratings=[SkillRating(skill="SQL", category=SkillCategory.SQL, rating=8)]
        )
        assert snap.average_rating == pytest.approx(8.0)

    def test_multiple_skills_mean(self) -> None:
        snap = SkillSnapshot(
            ratings=[
                SkillRating(skill="SQL", category=SkillCategory.SQL, rating=6),
                SkillRating(skill="Python", category=SkillCategory.PYTHON, rating=8),
                SkillRating(skill="Spark", category=SkillCategory.DATA_ENGINEERING, rating=4),
            ]
        )
        assert snap.average_rating == pytest.approx(6.0)


class TestSkillSnapshotWeakestStrongest:
    def _make_snap(self) -> SkillSnapshot:
        return SkillSnapshot(
            ratings=[
                SkillRating(skill="A", category=SkillCategory.SQL, rating=3),
                SkillRating(skill="B", category=SkillCategory.SQL, rating=7),
                SkillRating(skill="C", category=SkillCategory.SQL, rating=5),
                SkillRating(skill="D", category=SkillCategory.SQL, rating=1),
                SkillRating(skill="E", category=SkillCategory.SQL, rating=9),
            ]
        )

    def test_weakest_three(self) -> None:
        snap = self._make_snap()
        weakest = snap.weakest(3)
        assert len(weakest) == 3
        assert weakest[0].skill == "D"  # rating 1
        assert weakest[1].skill == "A"  # rating 3

    def test_strongest_one(self) -> None:
        snap = self._make_snap()
        strongest = snap.strongest(1)
        assert len(strongest) == 1
        assert strongest[0].skill == "E"  # rating 9

    def test_weakest_empty_snap(self) -> None:
        snap = SkillSnapshot(ratings=[])
        assert snap.weakest(3) == []


class TestSkillDeltaCompute:
    def test_up_trend(self) -> None:
        d = SkillDelta.compute("SQL", SkillCategory.SQL, previous=5, current=8)
        assert d.trend == "up"
        assert d.delta == 3
        assert d.previous_rating == 5
        assert d.current_rating == 8

    def test_down_trend(self) -> None:
        d = SkillDelta.compute("SQL", SkillCategory.SQL, previous=8, current=5)
        assert d.trend == "down"
        assert d.delta == -3

    def test_same_trend(self) -> None:
        d = SkillDelta.compute("SQL", SkillCategory.SQL, previous=6, current=6)
        assert d.trend == "same"
        assert d.delta == 0

    def test_skill_name_preserved(self) -> None:
        d = SkillDelta.compute("Apache Spark", SkillCategory.DATA_ENGINEERING, 4, 7)
        assert d.skill == "Apache Spark"
        assert d.category == SkillCategory.DATA_ENGINEERING
