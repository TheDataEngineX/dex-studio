"""Integration tests — ApplicationTracker full lifecycle (DuckDB-backed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from careerdex.models.application import (
    ApplicationEntry,
    ApplicationStatus,
)
from careerdex.services.tracker import ApplicationTracker


@pytest.fixture()
def tracker(tmp_path: Path) -> ApplicationTracker:
    t = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
    yield t
    t.close()


def _entry(**kwargs: object) -> ApplicationEntry:
    defaults: dict[str, object] = {"company": "Acme Corp", "position": "Data Engineer"}
    return ApplicationEntry(**{**defaults, **kwargs})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------


class TestApplicationTrackerCRUD:
    def test_add_returns_entry(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        result = tracker.add(e)
        assert result.id == e.id
        assert result.company == "Acme Corp"

    def test_get_returns_added_entry(self, tracker: ApplicationTracker) -> None:
        e = _entry(company="TechStart")
        tracker.add(e)
        retrieved = tracker.get(e.id)
        assert retrieved is not None
        assert retrieved.company == "TechStart"
        assert retrieved.position == "Data Engineer"

    def test_get_unknown_id_returns_none(self, tracker: ApplicationTracker) -> None:
        assert tracker.get("does-not-exist") is None

    def test_list_all_returns_all_entries(self, tracker: ApplicationTracker) -> None:
        for i in range(5):
            tracker.add(_entry(company=f"Co-{i}", position="SWE"))
        entries = tracker.list_all()
        assert len(entries) == 5

    def test_list_all_empty_returns_empty(self, tracker: ApplicationTracker) -> None:
        assert tracker.list_all() == []

    def test_total_reflects_count(self, tracker: ApplicationTracker) -> None:
        assert tracker.total() == 0
        tracker.add(_entry())
        tracker.add(_entry(company="Other Corp"))
        assert tracker.total() == 2

    def test_delete_existing_entry(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        assert tracker.delete(e.id) is True
        assert tracker.get(e.id) is None

    def test_delete_nonexistent_returns_false(self, tracker: ApplicationTracker) -> None:
        assert tracker.delete("nonexistent-id") is False

    def test_update_modifies_fields(self, tracker: ApplicationTracker) -> None:
        e = _entry(company="OldCo")
        tracker.add(e)
        e.company = "NewCo"
        tracker.update(e)
        refreshed = tracker.get(e.id)
        assert refreshed is not None
        assert refreshed.company == "NewCo"


# ---------------------------------------------------------------------------
# Filtering and search
# ---------------------------------------------------------------------------


class TestApplicationTrackerFiltering:
    def test_list_by_status_saved(self, tracker: ApplicationTracker) -> None:
        tracker.add(_entry(company="Saved Corp"))
        e2 = _entry(company="Applied Corp")
        tracker.add(e2)
        tracker.update_status(e2.id, ApplicationStatus.APPLIED)

        saved = tracker.list_all(status=ApplicationStatus.SAVED)
        assert len(saved) == 1
        assert saved[0].company == "Saved Corp"

    def test_list_by_status_applied(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        tracker.update_status(e.id, ApplicationStatus.APPLIED)

        applied = tracker.list_all(status=ApplicationStatus.APPLIED)
        assert len(applied) == 1

    def test_search_by_company_name(self, tracker: ApplicationTracker) -> None:
        tracker.add(_entry(company="DataCo Inc"))
        tracker.add(_entry(company="TechStart"))
        results = tracker.list_all(search="DataCo")
        assert len(results) == 1
        assert results[0].company == "DataCo Inc"

    def test_search_by_position_name(self, tracker: ApplicationTracker) -> None:
        tracker.add(_entry(position="Data Engineer"))
        tracker.add(_entry(position="Frontend Dev"))
        results = tracker.list_all(search="frontend")
        assert len(results) == 1
        assert results[0].position == "Frontend Dev"

    def test_search_no_match_returns_empty(self, tracker: ApplicationTracker) -> None:
        tracker.add(_entry(company="Acme Corp"))
        assert tracker.list_all(search="xyzzy-nonexistent") == []

    def test_search_case_insensitive(self, tracker: ApplicationTracker) -> None:
        tracker.add(_entry(company="SomeCorp"))
        results = tracker.list_all(search="SOMECORP")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


class TestApplicationStatusTransitions:
    def test_saved_to_applied(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        updated = tracker.update_status(e.id, ApplicationStatus.APPLIED)
        assert updated is not None
        assert updated.status == ApplicationStatus.APPLIED

    def test_applied_to_phone_screen(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        tracker.update_status(e.id, ApplicationStatus.APPLIED)
        updated = tracker.update_status(e.id, ApplicationStatus.PHONE_SCREEN)
        assert updated is not None
        assert updated.status == ApplicationStatus.PHONE_SCREEN

    def test_full_pipeline_to_offer(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        for status in [
            ApplicationStatus.APPLIED,
            ApplicationStatus.PHONE_SCREEN,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.FINAL_ROUND,
            ApplicationStatus.OFFER,
        ]:
            result = tracker.update_status(e.id, status)
            assert result is not None
            assert result.status == status

    def test_invalid_transition_raises_value_error(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        # SAVED → OFFER is not a valid direct transition
        with pytest.raises(ValueError, match="Cannot move"):
            tracker.update_status(e.id, ApplicationStatus.OFFER)

    def test_status_change_records_event(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        tracker.update_status(e.id, ApplicationStatus.APPLIED, reason="clicked apply")
        refreshed = tracker.get(e.id)
        assert refreshed is not None
        assert len(refreshed.events) == 1
        assert refreshed.events[0].to_status == ApplicationStatus.APPLIED
        assert refreshed.events[0].reason == "clicked apply"

    def test_applied_at_set_on_apply(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        assert e.applied_at is None
        tracker.update_status(e.id, ApplicationStatus.APPLIED)
        updated = tracker.get(e.id)
        assert updated is not None
        assert updated.applied_at is not None

    def test_update_status_unknown_id_raises(self, tracker: ApplicationTracker) -> None:
        with pytest.raises(KeyError):
            tracker.update_status("nonexistent", ApplicationStatus.APPLIED)

    def test_saved_to_rejected_via_applied(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        tracker.update_status(e.id, ApplicationStatus.APPLIED)
        updated = tracker.update_status(e.id, ApplicationStatus.REJECTED)
        assert updated is not None
        assert updated.status == ApplicationStatus.REJECTED


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class TestApplicationTrackerNotes:
    def test_add_note_persists(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        updated = tracker.add_note(e.id, "Called recruiter — very positive")
        assert updated is not None
        assert len(updated.notes) == 1
        assert updated.notes[0].text == "Called recruiter — very positive"

    def test_add_multiple_notes(self, tracker: ApplicationTracker) -> None:
        e = _entry()
        tracker.add(e)
        tracker.add_note(e.id, "Note A")
        tracker.add_note(e.id, "Note B")
        refreshed = tracker.get(e.id)
        assert refreshed is not None
        assert len(refreshed.notes) == 2
        texts = {n.text for n in refreshed.notes}
        assert texts == {"Note A", "Note B"}

    def test_add_note_unknown_id_returns_none(self, tracker: ApplicationTracker) -> None:
        result = tracker.add_note("nonexistent", "Some note")
        assert result is None

    def test_notes_survive_db_reload(self, tmp_path: Path) -> None:
        db = tmp_path / "notes_test.duckdb"
        t1 = ApplicationTracker(db_path=db)
        e = _entry()
        t1.add(e)
        t1.add_note(e.id, "Persistent note")
        t1.close()

        t2 = ApplicationTracker(db_path=db)
        refreshed = t2.get(e.id)
        assert refreshed is not None
        assert len(refreshed.notes) == 1
        assert refreshed.notes[0].text == "Persistent note"
        t2.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestApplicationTrackerStats:
    def test_stats_by_status(self, tracker: ApplicationTracker) -> None:
        e1 = _entry(company="A")
        e2 = _entry(company="B")
        e3 = _entry(company="C")
        tracker.add(e1)
        tracker.add(e2)
        tracker.add(e3)
        tracker.update_status(e2.id, ApplicationStatus.APPLIED)
        tracker.update_status(e3.id, ApplicationStatus.APPLIED)

        stats = tracker.stats()
        assert stats["saved"] == 1
        assert stats["applied"] == 2

    def test_stats_empty_tracker(self, tracker: ApplicationTracker) -> None:
        assert tracker.stats() == {}

    def test_total_counts_all(self, tracker: ApplicationTracker) -> None:
        for i in range(7):
            tracker.add(_entry(company=f"Co-{i}"))
        assert tracker.total() == 7


# ---------------------------------------------------------------------------
# Persistence (DB round-trip)
# ---------------------------------------------------------------------------


class TestApplicationTrackerPersistence:
    def test_entries_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "persist.duckdb"
        t1 = ApplicationTracker(db_path=db)
        e = _entry(company="PersistCo", position="ML Engineer")
        t1.add(e)
        t1.close()

        t2 = ApplicationTracker(db_path=db)
        entries = t2.list_all()
        assert len(entries) == 1
        assert entries[0].company == "PersistCo"
        t2.close()

    def test_salary_fields_persist(self, tmp_path: Path) -> None:
        db = tmp_path / "salary.duckdb"
        t1 = ApplicationTracker(db_path=db)
        e = _entry(salary_min=90_000.0, salary_max=130_000.0, salary_currency="EUR")
        t1.add(e)
        t1.close()

        t2 = ApplicationTracker(db_path=db)
        retrieved = t2.get(e.id)
        assert retrieved is not None
        assert retrieved.salary_min == 90_000.0
        assert retrieved.salary_max == 130_000.0
        assert retrieved.salary_currency == "EUR"
        t2.close()

    def test_tags_persist(self, tmp_path: Path) -> None:
        db = tmp_path / "tags.duckdb"
        t1 = ApplicationTracker(db_path=db)
        e = _entry(tags=["remote", "startup", "senior"])
        t1.add(e)
        t1.close()

        t2 = ApplicationTracker(db_path=db)
        retrieved = t2.get(e.id)
        assert retrieved is not None
        assert set(retrieved.tags) == {"remote", "startup", "senior"}
        t2.close()
