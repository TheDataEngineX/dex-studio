"""Graph models — CompanyNode and ConnectionEdge for tracking company relationships."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
    "ConnectionType",
    "CompanyNode",
    "ConnectionEdge",
]


class ConnectionType(StrEnum):
    """Type of relationship between companies."""

    COMPETITORS = "competitors"
    ACQUIRERS = "acquirers"
    PARTNERS = "partners"
    SIMILAR_SIZE = "similar_size"
    SAME_INDUSTRY = "same_industry"


class CompanyNode(BaseModel):
    """A company node in the graph."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    name: str
    url: str = ""
    industry: str = ""
    size: str = ""  # e.g., "1-10", "11-50", "51-200", "201-500", "501-1000", "1000-5000", "5000+"
    logo_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectionEdge(BaseModel):
    """An edge connecting two companies in the graph."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    source_company_id: str
    target_company_id: str
    connection_type: ConnectionType = ConnectionType.COMPETITORS
    strength: float = 1.0  # 0.0 to 1.0
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
