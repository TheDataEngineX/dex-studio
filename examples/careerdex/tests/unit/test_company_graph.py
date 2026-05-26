"""Tests for CompanyGraph — DuckDB-backed graph for tracking company connections."""

from __future__ import annotations

from pathlib import Path

import pytest

from careerdex.services.company_graph import CompanyGraph
from careerdex.services.graph import CompanyNode, ConnectionEdge


@pytest.fixture
def graph(tmp_path: Path) -> CompanyGraph:
    """Fresh graph backed by a temp DuckDB file — isolated per test."""
    g = CompanyGraph(db_path=tmp_path / "test_graph.duckdb")
    yield g
    g.close()


@pytest.fixture
def company() -> CompanyNode:
    return CompanyNode(
        name="Acme Corp",
        url="https://acme.com",
        industry="Technology",
        size="1000-5000",
        logo_url="https://acme.com/logo.png",
    )


class TestCompanyNodeModel:
    def test_company_node_creation(self, company: CompanyNode) -> None:
        assert company.name == "Acme Corp"
        assert company.url == "https://acme.com"
        assert company.industry == "Technology"
        assert company.size == "1000-5000"
        assert company.logo_url == "https://acme.com/logo.png"
        assert company.id != ""

    def test_company_node_with_metadata(self) -> None:
        company = CompanyNode(
            name="Beta Inc",
            url="https://beta.com",
            metadata={"founding_year": 2010, "headquarters": "NYC"},
        )
        assert company.metadata["founding_year"] == 2010
        assert company.metadata["headquarters"] == "NYC"


class TestConnectionEdgeModel:
    def test_connection_edge_creation(self) -> None:
        edge = ConnectionEdge(
            source_company_id="comp_a",
            target_company_id="comp_b",
            connection_type="competitors",
            strength=0.8,
        )
        assert edge.source_company_id == "comp_a"
        assert edge.target_company_id == "comp_b"
        assert edge.connection_type == "competitors"
        assert edge.strength == 0.8
        assert edge.id != ""

    def test_connection_edge_with_notes(self) -> None:
        edge = ConnectionEdge(
            source_company_id="comp_a",
            target_company_id="comp_b",
            connection_type="partners",
            strength=0.9,
            notes="Strategic partnership for cloud services",
        )
        assert edge.notes == "Strategic partnership for cloud services"


class TestCompanyGraphCRUD:
    def test_add_and_get_company(self, graph: CompanyGraph, company: CompanyNode) -> None:
        graph.add_company(company)
        fetched = graph.get_company(company.id)
        assert fetched is not None
        assert fetched.name == "Acme Corp"
        assert fetched.url == "https://acme.com"

    def test_get_company_not_found(self, graph: CompanyGraph) -> None:
        result = graph.get_company("nonexistent_id")
        assert result is None

    def test_update_company(self, graph: CompanyGraph, company: CompanyNode) -> None:
        graph.add_company(company)
        company.industry = "SaaS"
        company.size = "500-1000"
        graph.update_company(company)
        updated = graph.get_company(company.id)
        assert updated is not None
        assert updated.industry == "SaaS"
        assert updated.size == "500-1000"

    def test_add_connection(self, graph: CompanyGraph, company: CompanyNode) -> None:
        graph.add_company(company)
        company2 = CompanyNode(
            name="Beta Inc",
            url="https://beta.com",
            industry="Technology",
        )
        graph.add_company(company2)
        graph.add_connection(
            source_company_id=company.id,
            target_company_id=company2.id,
            connection_type="competitors",
            strength=0.85,
        )
        connections = graph.get_connections(company.id)
        assert len(connections) == 1
        assert connections[0].target_company_id == company2.id
        assert connections[0].connection_type == "competitors"

    def test_get_connections_not_found(self, graph: CompanyGraph) -> None:
        connections = graph.get_connections("nonexistent_id")
        assert connections == []

    def test_connection_types(self, graph: CompanyGraph, company: CompanyNode) -> None:
        graph.add_company(company)
        company2 = CompanyNode(name="Beta Inc", url="https://beta.com")
        company3 = CompanyNode(name="Gamma LLC", url="https://gamma.com")
        company4 = CompanyNode(name="Delta Co", url="https://delta.com")
        company5 = CompanyNode(name="Epsilon Inc", url="https://epsilon.com")
        graph.add_company(company2)
        graph.add_company(company3)
        graph.add_company(company4)
        graph.add_company(company5)

        graph.add_connection(company.id, company2.id, "competitors", 0.9)
        graph.add_connection(company.id, company3.id, "acquirers", 0.95)
        graph.add_connection(company.id, company4.id, "partners", 0.85)
        graph.add_connection(company.id, company5.id, "same_industry", 0.7)

        connections = graph.get_connections(company.id)
        assert len(connections) == 4

        types = {c.connection_type for c in connections}
        assert types == {"competitors", "acquirers", "partners", "same_industry"}
