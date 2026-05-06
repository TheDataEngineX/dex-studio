"""Unit tests for ApplicationTracker."""

from __future__ import annotations

from pathlib import Path

import pytest
from careerdex.models.application import (
    ApplicationEntry,
    ApplicationNote,
    ApplicationStatus,
)
from careerdex.services.tracker import ApplicationTracker


@pytest.fixture()
def tracker(tmp_path: Path) -> ApplicationTracker:
    return ApplicationTracker(db_path=tmp_path / "test.duckdb")


@pytest.fixture()
def entry() -> ApplicationEntry:
    return ApplicationEntry(company="Acme", position="Data Engineer")


class TestAdd:
    def test_returns_entry(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        result = tracker.add(entry)
        assert result.id == entry.id

    def test_persists(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        assert tracker.get(entry.id) is not None


class TestGet:
    def test_missing_returns_none(self, tracker: ApplicationTracker) -> None:
        assert tracker.get("does-not-exist") is None

    def test_round_trip(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        fetched = tracker.get(entry.id)
        assert fetched is not None
        assert fetched.company == "Acme"
        assert fetched.position == "Data Engineer"


class TestListAll:
    def test_empty(self, tracker: ApplicationTracker) -> None:
        assert tracker.list_all() == []

    def test_returns_all(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="A", position="SWE"))
        tracker.add(ApplicationEntry(company="B", position="MLE"))
        assert len(tracker.list_all()) == 2

    def test_filter_by_status(self, tracker: ApplicationTracker) -> None:
        e1 = ApplicationEntry(company="A", position="p1", status=ApplicationStatus.APPLIED)
        e2 = ApplicationEntry(company="B", position="p2", status=ApplicationStatus.SAVED)
        tracker.add(e1)
        tracker.add(e2)
        results = tracker.list_all(status=ApplicationStatus.APPLIED)
        assert len(results) == 1
        assert results[0].company == "A"

    def test_search_company_case_insensitive(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="AcmeCorp", position="SWE"))
        tracker.add(ApplicationEntry(company="Other", position="SWE"))
        results = tracker.list_all(search="acme")
        assert len(results) == 1
        assert results[0].company == "AcmeCorp"

    def test_search_position(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="X", position="Data Engineer"))
        tracker.add(ApplicationEntry(company="Y", position="Software Engineer"))
        results = tracker.list_all(search="data")
        assert len(results) == 1


class TestDelete:
    def test_missing_returns_false(self, tracker: ApplicationTracker) -> None:
        assert tracker.delete("nope") is False

    def test_existing_returns_true(
        self, tracker: ApplicationTracker, entry: ApplicationEntry
    ) -> None:
        tracker.add(entry)
        assert tracker.delete(entry.id) is True
        assert tracker.get(entry.id) is None


class TestUpdateStatus:
    def test_transitions_status(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        updated = tracker.update_status(entry.id, ApplicationStatus.APPLIED)
        assert updated is not None
        assert updated.status == ApplicationStatus.APPLIED

    def test_records_event(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        updated = tracker.update_status(
            entry.id, ApplicationStatus.APPLIED, reason="Applied online"
        )
        assert updated is not None
        assert len(updated.events) == 1

    def test_missing_raises(self, tracker: ApplicationTracker) -> None:
        with pytest.raises(KeyError):
            tracker.update_status("nope", ApplicationStatus.APPLIED)


class TestAddNote:
    def test_appends_note(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        updated = tracker.add_note(entry.id, "Great culture fit")
        assert updated is not None
        assert len(updated.notes) == 1
        assert updated.notes[0].text == "Great culture fit"

    def test_missing_returns_none(self, tracker: ApplicationTracker) -> None:
        assert tracker.add_note("nope", "note") is None


class TestStats:
    def test_empty_returns_empty_dict(self, tracker: ApplicationTracker) -> None:
        assert tracker.stats() == {}

    def test_counts_by_status(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="A", position="p", status=ApplicationStatus.SAVED))
        tracker.add(ApplicationEntry(company="B", position="p", status=ApplicationStatus.SAVED))
        tracker.add(ApplicationEntry(company="C", position="p", status=ApplicationStatus.APPLIED))
        stats = tracker.stats()
        assert stats["saved"] == 2
        assert stats["applied"] == 1

    def test_total(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="A", position="p"))
        tracker.add(ApplicationEntry(company="B", position="p"))
        assert tracker.total() == 2

    def test_total_empty(self, tracker: ApplicationTracker) -> None:
        assert tracker.total() == 0


class TestEdgeCases:
    def test_unicode_company_name(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="株式会社テスト", position="データエンジニア")
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.company == "株式会社テスト"

    def test_special_characters_in_position(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="Acme", position="Sr. Engineer (C++/Python)")
        entry.notes.append(ApplicationNote(text="Note with 'quotes' and \"double quotes\""))
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert "(" in result.position
        assert result.notes[0].text == "Note with 'quotes' and \"double quotes\""

    def test_newline_in_company(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="Acme\nCorp", position="SWE")
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert "\n" in result.company

    def test_empty_company_handled(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="", position="")
        result = tracker.add(entry)
        assert result.id is not None
        fetched = tracker.get(result.id)
        assert fetched is not None
        assert fetched.company == ""
        assert fetched.position == ""

    def test_salary_null_handles(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B", salary_min=None, salary_max=None)
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.salary_min is None
        assert result.salary_max is None

    def test_salary_values_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(
            company="A", position="B", salary_min=100000.0, salary_max=150000.0
        )
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.salary_min == 100000.0
        assert result.salary_max == 150000.0

    def test_tags_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B", tags=["urgent", "remote"])
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert "urgent" in result.tags
        assert "remote" in result.tags

    def test_empty_tags(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B", tags=[])
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.tags == []

    def test_source_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B", source="linkedin")
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.source == "linkedin"

    def test_contact_info_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(
            company="A",
            position="B",
            contact_name="John Doe",
            contact_email="john@example.com",
        )
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.contact_name == "John Doe"
        assert result.contact_email == "john@example.com"

    def test_location_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B", location="San Francisco, CA")
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.location == "San Francisco, CA"

    def test_url_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B", url="https://example.com/job/123")
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert result.url == "https://example.com/job/123"

    def test_multiple_notes_preserved(self, tracker: ApplicationTracker) -> None:
        entry = ApplicationEntry(company="A", position="B")
        entry.notes.append(ApplicationNote(text="Note 1"))
        entry.notes.append(ApplicationNote(text="Note 2"))
        tracker.add(entry)
        result = tracker.get(entry.id)
        assert result is not None
        assert len(result.notes) == 2
        assert result.notes[0].text == "Note 1"
        assert result.notes[1].text == "Note 2"

    def test_case_insensitive_search(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="GOOGLE", position="SWE"))
        tracker.add(ApplicationEntry(company="apple", position="PM"))
        results = tracker.list_all(search="GOOGLE")
        assert len(results) == 1
        assert results[0].company == "GOOGLE"

    def test_search_partial_match(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="The Great Company", position="Engineer"))
        results = tracker.list_all(search="Great")
        assert len(results) == 1

    def test_search_no_match(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="Acme", position="SWE"))
        results = tracker.list_all(search="xyz123")
        assert results == []

    def test_status_filter_and_search_combined(self, tracker: ApplicationTracker) -> None:
        e1 = ApplicationEntry(company="Acme", position="SWE", status=ApplicationStatus.APPLIED)
        e2 = ApplicationEntry(company="Acme", position="PM", status=ApplicationStatus.SAVED)
        tracker.add(e1)
        tracker.add(e2)
        results = tracker.list_all(status=ApplicationStatus.APPLIED, search="acme")
        assert len(results) == 1
        assert results[0].status == ApplicationStatus.APPLIED
