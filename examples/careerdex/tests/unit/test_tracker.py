"""Tests for ApplicationTracker — DuckDB-backed CRUD and status transitions."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from careerdex.models.application import ApplicationEntry, ApplicationStatus
from careerdex.services.tracker import ApplicationTracker


@pytest.fixture
def tracker(tmp_path: Path) -> ApplicationTracker:
    """Fresh tracker backed by a temp DuckDB file — isolated per test."""
    t = ApplicationTracker(db_path=tmp_path / "test.duckdb")
    yield t
    t.close()


@pytest.fixture
def entry() -> ApplicationEntry:
    return ApplicationEntry(
        company="Acme Corp", position="Data Engineer", url="https://acme.com/jobs/1"
    )


class TestAdd:
    def test_add_returns_entry(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        result = tracker.add(entry)
        assert result.id == entry.id
        assert result.company == "Acme Corp"

    def test_added_entry_is_retrievable(
        self, tracker: ApplicationTracker, entry: ApplicationEntry
    ) -> None:
        tracker.add(entry)
        fetched = tracker.get(entry.id)
        assert fetched is not None
        assert fetched.company == "Acme Corp"

    def test_duplicate_id_raises(
        self, tracker: ApplicationTracker, entry: ApplicationEntry
    ) -> None:
        tracker.add(entry)
        with pytest.raises(duckdb.Error):
            tracker.add(entry)

    def test_default_status_saved(self, tracker: ApplicationTracker) -> None:
        e = ApplicationEntry(company="X", position="Y")
        tracker.add(e)
        fetched = tracker.get(e.id)
        assert fetched is not None
        assert fetched.status == ApplicationStatus.SAVED


class TestListAll:
    def test_empty_tracker_returns_empty_list(self, tracker: ApplicationTracker) -> None:
        assert tracker.list_all() == []

    def test_lists_all_entries(self, tracker: ApplicationTracker) -> None:
        for i in range(3):
            tracker.add(ApplicationEntry(company=f"Co{i}", position="SWE"))
        assert len(tracker.list_all()) == 3

    def test_filter_by_status(self, tracker: ApplicationTracker) -> None:
        e1 = ApplicationEntry(company="A", position="SWE", status=ApplicationStatus.APPLIED)
        e2 = ApplicationEntry(company="B", position="SWE", status=ApplicationStatus.SAVED)
        tracker.add(e1)
        tracker.add(e2)
        applied = tracker.list_all(status=ApplicationStatus.APPLIED)
        assert len(applied) == 1
        assert applied[0].company == "A"

    def test_search_by_company(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="Stripe", position="SWE"))
        tracker.add(ApplicationEntry(company="Notion", position="SWE"))
        results = tracker.list_all(search="stripe")
        assert len(results) == 1
        assert results[0].company == "Stripe"


class TestUpdateStatus:
    def test_valid_transition(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        tracker.update_status(entry.id, ApplicationStatus.APPLIED)
        fetched = tracker.get(entry.id)
        assert fetched is not None
        assert fetched.status == ApplicationStatus.APPLIED

    def test_nonexistent_id_raises(self, tracker: ApplicationTracker) -> None:
        with pytest.raises(KeyError):
            tracker.update_status("nonexistent-id", ApplicationStatus.APPLIED)


class TestDelete:
    def test_delete_removes_entry(
        self, tracker: ApplicationTracker, entry: ApplicationEntry
    ) -> None:
        tracker.add(entry)
        tracker.delete(entry.id)
        assert tracker.get(entry.id) is None

    def test_list_after_delete_is_shorter(self, tracker: ApplicationTracker) -> None:
        e1 = ApplicationEntry(company="A", position="SWE")
        e2 = ApplicationEntry(company="B", position="SWE")
        tracker.add(e1)
        tracker.add(e2)
        tracker.delete(e1.id)
        assert len(tracker.list_all()) == 1
