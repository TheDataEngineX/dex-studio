"""Tests for ApplicationStatus state machine — all 13 statuses, all valid transitions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from careerdex.models.application import (
    STATUS_TRANSITIONS,
    ApplicationEntry,
    ApplicationStatus,
)


class TestApplicationStatusEnum:
    def test_all_statuses_defined(self) -> None:
        expected = {
            "saved",
            "applied",
            "reached_out",
            "responded",
            "phone_screen",
            "interview",
            "technical",
            "final_round",
            "offer",
            "accepted",
            "rejected",
            "withdrawn",
            "ghosted",
        }
        assert {s.value for s in ApplicationStatus} == expected

    def test_status_is_str(self) -> None:
        assert isinstance(ApplicationStatus.SAVED, str)
        assert ApplicationStatus.SAVED == "saved"


class TestStatusTransitions:
    def test_every_status_has_transition_entry(self) -> None:
        for status in ApplicationStatus:
            assert status in STATUS_TRANSITIONS, f"{status} missing from STATUS_TRANSITIONS"

    def test_saved_can_apply(self) -> None:
        assert ApplicationStatus.APPLIED in STATUS_TRANSITIONS[ApplicationStatus.SAVED]

    def test_saved_can_reach_out(self) -> None:
        assert ApplicationStatus.REACHED_OUT in STATUS_TRANSITIONS[ApplicationStatus.SAVED]

    def test_terminal_states_have_no_transitions(self) -> None:
        terminals = (
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        )
        for terminal in terminals:
            assert STATUS_TRANSITIONS[terminal] == [], f"{terminal} should be terminal"

    def test_offer_leads_to_accepted_or_rejected(self) -> None:
        transitions = STATUS_TRANSITIONS[ApplicationStatus.OFFER]
        assert ApplicationStatus.ACCEPTED in transitions
        assert ApplicationStatus.REJECTED in transitions

    def test_applied_can_be_ghosted(self) -> None:
        assert ApplicationStatus.GHOSTED in STATUS_TRANSITIONS[ApplicationStatus.APPLIED]

    def test_ghosted_can_recover(self) -> None:
        transitions = STATUS_TRANSITIONS[ApplicationStatus.GHOSTED]
        assert ApplicationStatus.RESPONDED in transitions

    def test_no_backward_skip_from_offer_to_applied(self) -> None:
        assert ApplicationStatus.APPLIED not in STATUS_TRANSITIONS[ApplicationStatus.OFFER]

    def test_interview_path_is_reachable(self) -> None:
        path = [
            ApplicationStatus.SAVED,
            ApplicationStatus.APPLIED,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
            ApplicationStatus.ACCEPTED,
        ]
        for i in range(len(path) - 1):
            assert path[i + 1] in STATUS_TRANSITIONS[path[i]], (
                f"Expected {path[i]} → {path[i + 1]} to be valid"
            )

    def test_all_transitions_target_valid_statuses(self) -> None:
        valid = set(ApplicationStatus)
        for status, targets in STATUS_TRANSITIONS.items():
            for t in targets:
                assert t in valid, f"Invalid target {t} from {status}"


class TestApplicationEntry:
    def test_default_status_is_saved(self) -> None:
        entry = ApplicationEntry(company="Acme", position="SWE")
        assert entry.status == ApplicationStatus.SAVED

    def test_id_auto_generated(self) -> None:
        a = ApplicationEntry(company="X", position="Y")
        b = ApplicationEntry(company="X", position="Y")
        assert a.id != b.id

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ApplicationEntry()  # type: ignore[call-arg]

    def test_position_field(self) -> None:
        entry = ApplicationEntry(company="Acme", position="Data Engineer")
        assert entry.position == "Data Engineer"

    def test_salary_optional(self) -> None:
        entry = ApplicationEntry(company="Acme", position="SWE")
        assert entry.salary_min is None
        assert entry.salary_max is None

    def test_tags_default_empty(self) -> None:
        entry = ApplicationEntry(company="Acme", position="SWE")
        assert entry.tags == []

    def test_notes_default_empty(self) -> None:
        entry = ApplicationEntry(company="Acme", position="SWE")
        assert entry.notes == []
