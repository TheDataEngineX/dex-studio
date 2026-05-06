"""Unit tests for NetworkingService."""

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
    return NetworkingService(db_path=tmp_path / "networking.duckdb")


@pytest.fixture()
def contact() -> NetworkContact:
    return NetworkContact(
        name="Alice Smith",
        title="Engineering Manager",
        company="Acme",
        relationship=ContactRelationship.HIRING_MANAGER,
    )


class TestAddGet:
    def test_round_trip(self, svc: NetworkingService, contact: NetworkContact) -> None:
        svc.add(contact)
        fetched = svc.get(contact.id)
        assert fetched is not None
        assert fetched.name == "Alice Smith"
        assert fetched.company == "Acme"
        assert fetched.relationship == ContactRelationship.HIRING_MANAGER

    def test_get_unknown_returns_none(self, svc: NetworkingService) -> None:
        assert svc.get("does-not-exist") is None


class TestListAll:
    def test_empty(self, svc: NetworkingService) -> None:
        assert svc.list_all() == []

    def test_returns_all(self, svc: NetworkingService) -> None:
        svc.add(NetworkContact(name="Alice", company="A"))
        svc.add(NetworkContact(name="Bob", company="B"))
        assert len(svc.list_all()) == 2

    def test_search_by_name(self, svc: NetworkingService) -> None:
        svc.add(NetworkContact(name="Alice Smith", company="Acme"))
        svc.add(NetworkContact(name="Bob Jones", company="Beta"))
        results = svc.list_all(search="alice")
        assert len(results) == 1
        assert results[0].name == "Alice Smith"

    def test_search_by_company(self, svc: NetworkingService) -> None:
        svc.add(NetworkContact(name="Alice", company="Acme Corp"))
        svc.add(NetworkContact(name="Bob", company="Beta Inc"))
        results = svc.list_all(search="acme")
        assert len(results) == 1


class TestDelete:
    def test_unknown_returns_false(self, svc: NetworkingService) -> None:
        assert svc.delete("nope") is False

    def test_existing_removes_contact(
        self, svc: NetworkingService, contact: NetworkContact
    ) -> None:
        svc.add(contact)
        assert svc.delete(contact.id) is True
        assert svc.get(contact.id) is None


class TestUpdate:
    def test_persists_name_change(self, svc: NetworkingService, contact: NetworkContact) -> None:
        svc.add(contact)
        contact.name = "Alice Johnson"
        svc.update(contact)
        fetched = svc.get(contact.id)
        assert fetched is not None
        assert fetched.name == "Alice Johnson"


class TestLogInteraction:
    def test_appends_interaction(self, svc: NetworkingService, contact: NetworkContact) -> None:
        svc.add(contact)
        interaction = Interaction(type=InteractionType.CALL, note="Great call")
        updated = svc.log_interaction(contact.id, interaction)
        assert updated is not None
        assert len(updated.interactions) == 1
        assert updated.interactions[0].note == "Great call"

    def test_unknown_contact_returns_none(self, svc: NetworkingService) -> None:
        interaction = Interaction(type=InteractionType.EMAIL)
        assert svc.log_interaction("nope", interaction) is None

    def test_multiple_interactions_stack(
        self, svc: NetworkingService, contact: NetworkContact
    ) -> None:
        svc.add(contact)
        svc.log_interaction(contact.id, Interaction(type=InteractionType.EMAIL))
        svc.log_interaction(contact.id, Interaction(type=InteractionType.CALL))
        fetched = svc.get(contact.id)
        assert fetched is not None
        assert len(fetched.interactions) == 2


class TestDueFollowUps:
    def test_returns_overdue(self, svc: NetworkingService) -> None:
        c = NetworkContact(
            name="Overdue",
            next_follow_up=datetime.now(UTC) - timedelta(days=1),
        )
        svc.add(c)
        due = svc.due_follow_ups()
        assert len(due) == 1
        assert due[0].name == "Overdue"

    def test_excludes_future(self, svc: NetworkingService) -> None:
        c = NetworkContact(
            name="Future",
            next_follow_up=datetime.now(UTC) + timedelta(days=7),
        )
        svc.add(c)
        assert svc.due_follow_ups() == []

    def test_excludes_no_follow_up(self, svc: NetworkingService) -> None:
        svc.add(NetworkContact(name="No followup"))
        assert svc.due_follow_ups() == []


class TestStats:
    def test_total(self, svc: NetworkingService) -> None:
        svc.add(NetworkContact(name="A"))
        svc.add(NetworkContact(name="B"))
        stats = svc.stats()
        assert stats["total"] == 2

    def test_due_follow_ups_count(self, svc: NetworkingService) -> None:
        svc.add(
            NetworkContact(
                name="Due",
                next_follow_up=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        svc.add(NetworkContact(name="No due"))
        stats = svc.stats()
        assert stats["due_follow_ups"] == 1

    def test_empty(self, svc: NetworkingService) -> None:
        stats = svc.stats()
        assert stats["total"] == 0
        assert stats["due_follow_ups"] == 0


class TestClose:
    def test_close_does_not_raise(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        svc.close()  # should not raise


class TestGenerateOutreach:
    import json
    import unittest.mock

    def test_suggest_outreach_success(self, svc: NetworkingService) -> None:
        import json
        import unittest.mock

        contact = NetworkContact(name="Alice", title="EM", company="TechCorp")
        svc.add(contact)

        payload = json.dumps(
            {
                "subject": "Quick hello",
                "message": "Hi Alice, I'd love to connect.",
                "tips": ["Be concise", "Mention shared interest"],
            }
        )
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {"response": payload}
        mock_resp.raise_for_status.return_value = None

        with unittest.mock.patch("httpx.post", return_value=mock_resp):
            result = svc.suggest_outreach(contact)

        assert "subject" in result
        assert "message" in result

    def test_suggest_outreach_raises_on_ollama_failure(self, svc: NetworkingService) -> None:
        import unittest.mock

        import httpx
        import pytest

        contact = NetworkContact(name="Bob", company="Corp")
        err = httpx.ConnectError("down")
        with (
            unittest.mock.patch("httpx.post", side_effect=err),
            pytest.raises(RuntimeError, match="Ollama"),
        ):
            svc.suggest_outreach(contact)


class TestNetworkingEdgeCases:
    def test_unicode_name(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        contact = NetworkContact(name="田中太郎", company="会社", title="エンジニア")
        svc.add(contact)
        result = svc.get(contact.id)
        assert result is not None
        assert result.name == "田中太郎"

    def test_special_chars_in_notes(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        contact = NetworkContact(name="Alice", company="Acme")
        svc.add(contact)
        interaction = Interaction(
            type=InteractionType.CALL,
            note="Discussed 'offer' and \"salary\"",
        )
        svc.log_interaction(contact.id, interaction)
        result = svc.get(contact.id)
        assert result is not None
        assert "'offer'" in result.interactions[0].note

    def test_empty_search_returns_all(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        svc.add(NetworkContact(name="A", company="C1"))
        svc.add(NetworkContact(name="B", company="C2"))
        results = svc.list_all(search="")
        assert len(results) == 2

    def test_search_case_insensitive(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        svc.add(NetworkContact(name="ALICE SMITH", company="Acme"))
        results = svc.list_all(search="alice")
        assert len(results) == 1

    def test_linkedin_url_preserved(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        contact = NetworkContact(
            name="Alice",
            company="Acme",
            linkedin_url="https://linkedin.com/in/alice",
        )
        svc.add(contact)
        result = svc.get(contact.id)
        assert result is not None
        assert result.linkedin_url == "https://linkedin.com/in/alice"

    def test_email_preserved(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        contact = NetworkContact(name="Alice", company="Acme", email="alice@acme.com")
        svc.add(contact)
        result = svc.get(contact.id)
        assert result is not None
        assert result.email == "alice@acme.com"

    def test_interaction_types_stored(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        contact = NetworkContact(name="Alice", company="Acme")
        svc.add(contact)
        for itype in InteractionType:
            svc.log_interaction(contact.id, Interaction(type=itype))
        result = svc.get(contact.id)
        assert result is not None
        assert len(result.interactions) == len(InteractionType)

    def test_all_relationship_types(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        for rel in ContactRelationship:
            contact = NetworkContact(name="Test", relationship=rel)
            svc.add(contact)
            result = svc.get(contact.id)
            assert result is not None
            assert result.relationship == rel
