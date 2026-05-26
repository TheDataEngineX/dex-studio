"""Vector database management for AI Engineers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VectorStoreType(StrEnum):
    DUCKDB_VSS = "duckdb_vss"
    QDRANT = "qdrant"
    LANCEDB = "lancedb"
    CHROMA = "chroma"
    PINECONE = "pinecone"


class CollectionStatus(StrEnum):
    ACTIVE = "active"
    BUILDING = "building"
    ERROR = "error"


class VectorCollection(BaseModel):
    """A vector collection for storing embeddings."""

    id: str
    name: str
    description: str = ""
    store_type: VectorStoreType
    dimension: int = 384
    metric: str = "cosine"
    document_count: int = 0
    status: CollectionStatus = CollectionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingDocument(BaseModel):
    """A document stored in a vector collection."""

    id: str
    content: str
    embedding: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    vector_id: str | None = None


class VectorSearchResult(BaseModel):
    """Result of a vector similarity search."""

    id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectionStats(BaseModel):
    """Statistics for a vector collection."""

    total_documents: int
    total_vectors: int
    index_size_mb: float
    avg_chunk_size: int
    last_updated: datetime
