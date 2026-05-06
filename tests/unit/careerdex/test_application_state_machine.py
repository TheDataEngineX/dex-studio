"""Comprehensive tests for the ApplicationEntry state machine and edge cases.

Covers the full STATUS_TRANSITIONS matrix, terminal states, multi-hop
paths, and boundary conditions not addressed by test_tracker.py.
"""

from __future__ import annotations

import pytest
from careerdex.models.application import (
    STATUS_TRANSITIONS,
    ApplicationEntry,
    ApplicationStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entry(status: ApplicationStatus = ApplicationStatus.SAVED) -> ApplicationEntry:
    e = ApplicationEntry(company="Acme", position="SWE")
    e.status = status
    return e


# ---------------------------------------------------------------------------
# can_transition — exhaustive matrix
# ---------------------------------------------------------------------------


class TestCanTransition:
    @pytest.mark.parametrize(
        ("from_s", "to_s", "expected"),
        [
            # SAVED valid
            (ApplicationStatus.SAVED, ApplicationStatus.APPLIED, True),
            (ApplicationStatus.SAVED, ApplicationStatus.REACHED_OUT, True),
            (ApplicationStatus.SAVED, ApplicationStatus.WITHDRAWN, True),
            # SAVED invalid
            (ApplicationStatus.SAVED, ApplicationStatus.OFFER, False),
            (ApplicationStatus.SAVED, ApplicationStatus.ACCEPTED, False),
            (ApplicationStatus.SAVED, ApplicationStatus.INTERVIEW, False),
            # APPLIED valid
            (ApplicationStatus.APPLIED, ApplicationStatus.PHONE_SCREEN, True),
            (ApplicationStatus.APPLIED, ApplicationStatus.RESPONDED, True),
            (ApplicationStatus.APPLIED, ApplicationStatus.REJECTED, True),
            (ApplicationStatus.APPLIED, ApplicationStatus.GHOSTED, True),
            (ApplicationStatus.APPLIED, ApplicationStatus.WITHDRAWN, True),
            # APPLIED invalid
            (ApplicationStatus.APPLIED, ApplicationStatus.ACCEPTED, False),
            (ApplicationStatus.APPLIED, ApplicationStatus.OFFER, False),
            # OFFER valid
            (ApplicationStatus.OFFER, ApplicationStatus.ACCEPTED, True),
            (ApplicationStatus.OFFER, ApplicationStatus.REJECTED, True),
            (ApplicationStatus.OFFER, ApplicationStatus.WITHDRAWN, True),
            # OFFER invalid
            (ApplicationStatus.OFFER, ApplicationStatus.SAVED, False),
            (ApplicationStatus.OFFER, ApplicationStatus.PHONE_SCREEN, False),
            # Terminal states — no transitions
            (ApplicationStatus.ACCEPTED, ApplicationStatus.WITHDRAWN, False),
            (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, False),
            (ApplicationStatus.REJECTED, ApplicationStatus.APPLIED, False),
            (ApplicationStatus.REJECTED, ApplicationStatus.INTERVIEW, False),
            (ApplicationStatus.WITHDRAWN, ApplicationStatus.SAVED, False),
            (ApplicationStatus.WITHDRAWN, ApplicationStatus.APPLIED, False),
            # GHOSTED can recover
            (ApplicationStatus.GHOSTED, ApplicationStatus.RESPONDED, True),
            (ApplicationStatus.GHOSTED, ApplicationStatus.WITHDRAWN, True),
            (ApplicationStatus.GHOSTED, ApplicationStatus.APPLIED, False),
        ],
    )
    def test_transition_matrix(
        self,
        from_s: ApplicationStatus,
        to_s: ApplicationStatus,
        expected: bool,
    ) -> None:
        entry = _entry(from_s)
        assert entry.can_transition(to_s) is expected


class TestTerminalStates:
    @pytest.mark.parametrize(
        "terminal",
        [ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
    )
    def test_terminal_state_has_no_valid_transitions(self, terminal: ApplicationStatus) -> None:
        assert STATUS_TRANSITIONS[terminal] == []

    @pytest.mark.parametrize(
        "terminal",
        [ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN],
    )
    def test_transition_from_terminal_raises(self, terminal: ApplicationStatus) -> None:
        entry = _entry(terminal)
        with pytest.raises(ValueError, match="Cannot move from"):
            entry.transition(ApplicationStatus.APPLIED)


# ---------------------------------------------------------------------------
# transition — happy paths
# ---------------------------------------------------------------------------


class TestTransitionHappyPath:
    def test_simple_transition_updates_status(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED)
        assert entry.status == ApplicationStatus.APPLIED

    def test_transition_records_event(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED, reason="Applied via LinkedIn")
        assert len(entry.events) == 1
        ev = entry.events[0]
        assert ev.from_status == ApplicationStatus.SAVED
        assert ev.to_status == ApplicationStatus.APPLIED
        assert ev.reason == "Applied via LinkedIn"

    def test_first_applied_sets_applied_at(self) -> None:
        entry = _entry()
        assert entry.applied_at is None
        entry.transition(ApplicationStatus.APPLIED)
        assert entry.applied_at is not None

    def test_second_transition_does_not_overwrite_applied_at(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED)
        first_applied_at = entry.applied_at
        entry.transition(ApplicationStatus.PHONE_SCREEN)
        assert entry.applied_at == first_applied_at

    def test_multiple_events_accumulate(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED)
        entry.transition(ApplicationStatus.PHONE_SCREEN)
        entry.transition(ApplicationStatus.INTERVIEW)
        assert len(entry.events) == 3
        assert entry.events[-1].to_status == ApplicationStatus.INTERVIEW

    def test_updated_at_changes_on_transition(self) -> None:
        entry = _entry()
        before = entry.updated_at
        entry.transition(ApplicationStatus.APPLIED)
        assert entry.updated_at >= before

    def test_empty_reason_is_valid(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED, reason="")
        assert entry.events[0].reason == ""


class TestTransitionErrors:
    def test_invalid_transition_raises_value_error(self) -> None:
        entry = _entry(ApplicationStatus.SAVED)
        with pytest.raises(ValueError, match="Cannot move from saved to accepted"):
            entry.transition(ApplicationStatus.ACCEPTED)

    def test_same_status_transition_raises(self) -> None:
        """Self-transition should always fail — SAVED is not in its own allowed list."""
        entry = _entry(ApplicationStatus.SAVED)
        with pytest.raises(ValueError):
            entry.transition(ApplicationStatus.SAVED)

    def test_backward_transition_raises(self) -> None:
        """PHONE_SCREEN → SAVED is never valid."""
        entry = _entry(ApplicationStatus.PHONE_SCREEN)
        with pytest.raises(ValueError):
            entry.transition(ApplicationStatus.SAVED)


# ---------------------------------------------------------------------------
# Full lifecycle paths
# ---------------------------------------------------------------------------


class TestFullLifecyclePaths:
    def test_offer_accepted_path(self) -> None:
        entry = _entry()
        path = [
            ApplicationStatus.APPLIED,
            ApplicationStatus.PHONE_SCREEN,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
            ApplicationStatus.ACCEPTED,
        ]
        for status in path:
            entry.transition(status)
        assert entry.status == ApplicationStatus.ACCEPTED
        assert len(entry.events) == 5

    def test_rejection_path(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED)
        entry.transition(ApplicationStatus.REJECTED)
        assert entry.status == ApplicationStatus.REJECTED

    def test_ghost_then_respond_path(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.APPLIED)
        entry.transition(ApplicationStatus.GHOSTED)
        entry.transition(ApplicationStatus.RESPONDED)
        assert entry.status == ApplicationStatus.RESPONDED

    def test_reached_out_to_applied_path(self) -> None:
        entry = _entry()
        entry.transition(ApplicationStatus.REACHED_OUT)
        entry.transition(ApplicationStatus.APPLIED)
        entry.transition(ApplicationStatus.INTERVIEW)
        assert entry.status == ApplicationStatus.INTERVIEW


# ---------------------------------------------------------------------------
# Model field edge cases
# ---------------------------------------------------------------------------


class TestApplicationEntryFields:
    def test_default_status_is_saved(self) -> None:
        entry = ApplicationEntry(company="X", position="Y")
        assert entry.status == ApplicationStatus.SAVED

    def test_empty_notes_and_events_on_creation(self) -> None:
        entry = ApplicationEntry(company="X", position="Y")
        assert entry.notes == []
        assert entry.events == []

    def test_unique_ids(self) -> None:
        e1 = ApplicationEntry(company="A", position="B")
        e2 = ApplicationEntry(company="A", position="B")
        assert e1.id != e2.id

    def test_salary_min_none_is_valid(self) -> None:
        entry = ApplicationEntry(company="X", position="Y", salary_min=None, salary_max=None)
        assert entry.salary_min is None
        assert entry.salary_max is None

    def test_salary_values_accepted(self) -> None:
        entry = ApplicationEntry(company="X", position="Y", salary_min=50_000, salary_max=120_000)
        assert entry.salary_min == 50_000
        assert entry.salary_max == 120_000

    def test_zero_salary_accepted(self) -> None:
        """Zero salary is unusual but valid (internship/volunteer)."""
        entry = ApplicationEntry(company="X", position="Y", salary_min=0.0, salary_max=0.0)
        assert entry.salary_min == 0.0

    def test_tags_default_empty(self) -> None:
        entry = ApplicationEntry(company="X", position="Y")
        assert entry.tags == []

    def test_unicode_company_name(self) -> None:
        entry = ApplicationEntry(company="株式会社テスト", position="SWE")
        assert entry.company == "株式会社テスト"

    def test_unicode_position(self) -> None:
        entry = ApplicationEntry(company="X", position="Développeur Senior")
        assert entry.position == "Développeur Senior"

    def test_url_empty_string_default(self) -> None:
        entry = ApplicationEntry(company="X", position="Y")
        assert entry.url == ""

    def test_status_transitions_covers_all_statuses(self) -> None:
        """Every ApplicationStatus must have an entry in STATUS_TRANSITIONS."""
        for status in ApplicationStatus:
            assert status in STATUS_TRANSITIONS, f"{status} missing from STATUS_TRANSITIONS"
