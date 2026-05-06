"""Integration tests — NetworkingService full lifecycle (DuckDB-backed)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from careerdex.models.networking import (
    ContactRelationship,
    Interaction,
    InteractionType,
    NetworkContact,
)
from careerdex.services.networking import NetworkingService


@pytest.fixture()
def svc(tmp_path: Path) -> NetworkingService:
    s = NetworkingService(db_path=tmp_path / "networking.duckdb")
    yield s
    s.close()


def _contact(**kwargs: object) -> NetworkContact:
    defaults: dict[str, object] = {
        "name": "Alice Smith",
        "company": "TechCorp",
        "title": "Engineering Manager",
    }
    return NetworkContact(**{**defaults, **kwargs})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------


class TestNetworkingServiceCRUD:
    def test_add_returns_contact(self, svc: NetworkingService) -> None:
        c = _contact()
        result = svc.add(c)
        assert result.id == c.id
        assert result.name == "Alice Smith"

    def test_get_returns_added_contact(self, svc: NetworkingService) -> None:
        c = _contact(name="Bob Jones")
        svc.add(c)
        retrieved = svc.get(c.id)
        assert retrieved is not None
        assert retrieved.name == "Bob Jones"
        assert retrieved.company == "TechCorp"

    def test_get_unknown_id_returns_none(self, svc: NetworkingService) -> None:
        assert svc.get("no-such-id") is None

    def test_list_all_returns_all_contacts(self, svc: NetworkingService) -> None:
        for i in range(4):
            svc.add(_contact(name=f"Person-{i}"))
        contacts = svc.list_all()
        assert len(contacts) == 4

    def test_list_all_empty_returns_empty(self, svc: NetworkingService) -> None:
        assert svc.list_all() == []

    def test_delete_existing_contact(self, svc: NetworkingService) -> None:
        c = _contact()
        svc.add(c)
        assert svc.delete(c.id) is True
        assert svc.get(c.id) is None

    def test_delete_nonexistent_returns_false(self, svc: NetworkingService) -> None:
        assert svc.delete("nonexistent") is False

    def test_update_modifies_fields(self, svc: NetworkingService) -> None:
        c = _contact(title="IC")
        svc.add(c)
        c.title = "Director of Engineering"
        svc.update(c)
        refreshed = svc.get(c.id)
        assert refreshed is not None
        assert refreshed.title == "Director of Engineering"


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------


class TestNetworkingContactRelationships:
    def test_recruiter_relationship(self, svc: NetworkingService) -> None:
        c = _contact(relationship=ContactRelationship.RECRUITER)
        svc.add(c)
        retrieved = svc.get(c.id)
        assert retrieved is not None
        assert retrieved.relationship == ContactRelationship.RECRUITER

    def test_hiring_manager_relationship(self, svc: NetworkingService) -> None:
        c = _contact(relationship=ContactRelationship.HIRING_MANAGER)
        svc.add(c)
        retrieved = svc.get(c.id)
        assert retrieved is not None
        assert retrieved.relationship == ContactRelationship.HIRING_MANAGER

    def test_mentor_relationship(self, svc: NetworkingService) -> None:
        c = _contact(relationship=ContactRelationship.MENTOR)
        svc.add(c)
        retrieved = svc.get(c.id)
        assert retrieved is not None
        assert retrieved.relationship == ContactRelationship.MENTOR

    def test_all_relationships_stored(self, svc: NetworkingService) -> None:
        for rel in ContactRelationship:
            svc.add(_contact(name=f"Person-{rel}", relationship=rel))
        contacts = svc.list_all()
        assert len(contacts) == len(ContactRelationship)


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------


class TestNetworkingInteractions:
    def test_log_interaction_appends_to_contact(self, svc: NetworkingService) -> None:
        c = _contact()
        svc.add(c)
        interaction = Interaction(type=InteractionType.EMAIL, note="Sent intro email")
        updated = svc.log_interaction(c.id, interaction)
        assert updated is not None
        assert len(updated.interactions) == 1
        assert updated.interactions[0].type == InteractionType.EMAIL

    def test_log_multiple_interactions(self, svc: NetworkingService) -> None:
        c = _contact()
        svc.add(c)
        svc.log_interaction(c.id, Interaction(type=InteractionType.EMAIL, note="Email 1"))
        svc.log_interaction(c.id, Interaction(type=InteractionType.CALL, note="Call 1"))
        svc.log_interaction(c.id, Interaction(type=InteractionType.MEETING, note="Meeting"))
        refreshed = svc.get(c.id)
        assert refreshed is not None
        assert len(refreshed.interactions) == 3

    def test_log_interaction_unknown_id_returns_none(self, svc: NetworkingService) -> None:
        result = svc.log_interaction("nonexistent", Interaction(type=InteractionType.EMAIL))
        assert result is None

    def test_interaction_note_preserved(self, svc: NetworkingService) -> None:
        c = _contact()
        svc.add(c)
        svc.log_interaction(c.id, Interaction(type=InteractionType.COFFEE_CHAT, note="Great chat"))
        refreshed = svc.get(c.id)
        assert refreshed is not None
        assert refreshed.interactions[0].note == "Great chat"

    def test_interaction_outcome_preserved(self, svc: NetworkingService) -> None:
        c = _contact()
        svc.add(c)
        svc.log_interaction(
            c.id,
            Interaction(type=InteractionType.REFERRAL_REQUESTED, outcome="referral pending"),
        )
        refreshed = svc.get(c.id)
        assert refreshed is not None
        assert refreshed.interactions[0].outcome == "referral pending"

    def test_last_contact_reflects_latest_interaction(self, svc: NetworkingService) -> None:
        c = _contact()
        svc.add(c)
        svc.log_interaction(c.id, Interaction(type=InteractionType.EMAIL))
        svc.log_interaction(c.id, Interaction(type=InteractionType.CALL))
        refreshed = svc.get(c.id)
        assert refreshed is not None
        assert refreshed.last_contact is not None
        assert refreshed.interaction_count == 2


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestNetworkingSearch:
    def test_search_by_name(self, svc: NetworkingService) -> None:
        svc.add(_contact(name="Alice Smith"))
        svc.add(_contact(name="Bob Jones"))
        results = svc.list_all(search="alice")
        assert len(results) == 1
        assert results[0].name == "Alice Smith"

    def test_search_by_company(self, svc: NetworkingService) -> None:
        svc.add(_contact(name="Alice", company="DataCorp"))
        svc.add(_contact(name="Bob", company="TechStart"))
        results = svc.list_all(search="datacorp")
        assert len(results) == 1
        assert results[0].company == "DataCorp"

    def test_search_no_match_returns_empty(self, svc: NetworkingService) -> None:
        svc.add(_contact(name="Alice"))
        assert svc.list_all(search="xyzzy") == []

    def test_search_case_insensitive(self, svc: NetworkingService) -> None:
        svc.add(_contact(name="ALICE SMITH"))
        results = svc.list_all(search="alice")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Due follow-ups
# ---------------------------------------------------------------------------


class TestNetworkingDueFollowUps:
    def test_due_followup_included(self, svc: NetworkingService) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        c = _contact(next_follow_up=past)
        svc.add(c)
        due = svc.due_follow_ups()
        assert len(due) == 1
        assert due[0].id == c.id

    def test_future_followup_not_included(self, svc: NetworkingService) -> None:
        future = datetime.now(UTC) + timedelta(days=7)
        c = _contact(next_follow_up=future)
        svc.add(c)
        due = svc.due_follow_ups()
        assert len(due) == 0

    def test_no_followup_date_not_included(self, svc: NetworkingService) -> None:
        c = _contact()  # next_follow_up = None
        svc.add(c)
        due = svc.due_follow_ups()
        assert len(due) == 0

    def test_multiple_due_followups_ordered(self, svc: NetworkingService) -> None:
        c1 = _contact(name="Oldest", next_follow_up=datetime.now(UTC) - timedelta(days=3))
        c2 = _contact(name="Recent", next_follow_up=datetime.now(UTC) - timedelta(hours=1))
        svc.add(c1)
        svc.add(c2)
        due = svc.due_follow_ups()
        assert len(due) == 2
        assert due[0].name == "Oldest"  # ordered by follow-up date ASC


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestNetworkingStats:
    def test_stats_total(self, svc: NetworkingService) -> None:
        for i in range(3):
            svc.add(_contact(name=f"Person-{i}"))
        s = svc.stats()
        assert s["total"] == 3

    def test_stats_by_relationship(self, svc: NetworkingService) -> None:
        svc.add(_contact(relationship=ContactRelationship.RECRUITER))
        svc.add(_contact(name="Another", relationship=ContactRelationship.RECRUITER))
        svc.add(_contact(name="Third", relationship=ContactRelationship.MENTOR))
        s = svc.stats()
        assert s["recruiter"] == 2
        assert s["mentor"] == 1

    def test_stats_due_followups_count(self, svc: NetworkingService) -> None:
        svc.add(_contact(next_follow_up=datetime.now(UTC) - timedelta(hours=1)))
        svc.add(_contact(name="Another", next_follow_up=datetime.now(UTC) - timedelta(hours=2)))
        svc.add(_contact(name="Future", next_follow_up=datetime.now(UTC) + timedelta(days=1)))
        s = svc.stats()
        assert s["due_follow_ups"] == 2

    def test_stats_empty_service(self, svc: NetworkingService) -> None:
        s = svc.stats()
        assert s["total"] == 0
        assert s["due_follow_ups"] == 0


# ---------------------------------------------------------------------------
# Persistence (DB round-trip)
# ---------------------------------------------------------------------------


class TestNetworkingPersistence:
    def test_contacts_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "net.duckdb"
        s1 = NetworkingService(db_path=db)
        c = _contact(name="Persistent Alice", email="alice@example.com")
        s1.add(c)
        s1.close()

        s2 = NetworkingService(db_path=db)
        contacts = s2.list_all()
        assert len(contacts) == 1
        assert contacts[0].name == "Persistent Alice"
        assert contacts[0].email == "alice@example.com"
        s2.close()

    def test_interactions_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "net.duckdb"
        s1 = NetworkingService(db_path=db)
        c = _contact()
        s1.add(c)
        s1.log_interaction(c.id, Interaction(type=InteractionType.CALL, note="Warm call"))
        s1.close()

        s2 = NetworkingService(db_path=db)
        retrieved = s2.get(c.id)
        assert retrieved is not None
        assert len(retrieved.interactions) == 1
        assert retrieved.interactions[0].note == "Warm call"
        s2.close()

    def test_tags_survive_reconnect(self, tmp_path: Path) -> None:
        db = tmp_path / "net.duckdb"
        s1 = NetworkingService(db_path=db)
        c = _contact(tags=["ml", "senior", "remote"])
        s1.add(c)
        s1.close()

        s2 = NetworkingService(db_path=db)
        retrieved = s2.get(c.id)
        assert retrieved is not None
        assert set(retrieved.tags) == {"ml", "senior", "remote"}
        s2.close()
