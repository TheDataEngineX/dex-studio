"""Vector database management service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog

from careerdex.models.vector_db import (
    CollectionStats,
    CollectionStatus,
    VectorCollection,
    VectorSearchResult,
    VectorStoreType,
)

logger = structlog.get_logger(__name__)

__all__ = ["VectorDBService"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "vectors.duckdb"


class VectorDBService:
    """Service for managing vector databases."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._init_tables()
        logger.info("vector_db_service_ready", db=str(self._db_path))

    def _init_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS collections (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR DEFAULT '',
                store_type VARCHAR,
                dimension INTEGER DEFAULT 384,
                metric VARCHAR DEFAULT 'cosine',
                document_count INTEGER DEFAULT 0,
                status VARCHAR DEFAULT 'active',
                metadata_json VARCHAR DEFAULT '{}',
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id VARCHAR PRIMARY KEY,
                collection_id VARCHAR,
                content TEXT,
                metadata_json VARCHAR DEFAULT '{}',
                vector_id VARCHAR,
                created_at TIMESTAMP,
                FOREIGN KEY (collection_id) REFERENCES collections(id)
            )
            """
        )

    def create_collection(self, collection: VectorCollection) -> VectorCollection:
        self._conn.execute(
            """
            INSERT INTO collections (id, name, description, store_type, dimension, metric, document_count, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,  # noqa: E501
            [
                collection.id,
                collection.name,
                collection.description,
                collection.store_type.value,
                collection.dimension,
                collection.metric,
                collection.document_count,
                collection.status.value,
                json.dumps(collection.metadata),
                collection.created_at.isoformat(),
                collection.updated_at.isoformat(),
            ],
        )
        logger.info("collection_created", id=collection.id, name=collection.name)
        return collection

    def get_collection(self, collection_id: str) -> VectorCollection | None:
        row = self._conn.execute(
            "SELECT * FROM collections WHERE id = ?", [collection_id]
        ).fetchone()
        if not row:
            return None
        return self._row_to_collection(row)

    def list_collections(self) -> list[VectorCollection]:
        rows = self._conn.execute("SELECT * FROM collections ORDER BY updated_at DESC").fetchall()
        return [self._row_to_collection(row) for row in rows]

    def update_collection(self, collection: VectorCollection) -> None:
        collection.updated_at = datetime.now()
        self._conn.execute(
            """
            UPDATE collections SET name = ?, description = ?, store_type = ?, dimension = ?, metric = ?, document_count = ?, status = ?, metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,  # noqa: E501
            [
                collection.name,
                collection.description,
                collection.store_type.value,
                collection.dimension,
                collection.metric,
                collection.document_count,
                collection.status.value,
                json.dumps(collection.metadata),
                collection.updated_at.isoformat(),
                collection.id,
            ],
        )

    def delete_collection(self, collection_id: str) -> bool:
        self._conn.execute("DELETE FROM documents WHERE collection_id = ?", [collection_id])
        self._conn.execute("DELETE FROM collections WHERE id = ?", [collection_id])
        return True

    def add_document(
        self, collection_id: str, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        doc_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO documents (id, collection_id, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                doc_id,
                collection_id,
                content,
                json.dumps(metadata or {}),
                datetime.now().isoformat(),
            ],
        )
        self._conn.execute(
            "UPDATE collections SET document_count = document_count + 1, updated_at = ? WHERE id = ?",  # noqa: E501
            [datetime.now().isoformat(), collection_id],
        )
        return doc_id

    def get_documents(self, collection_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM documents WHERE collection_id = ? ORDER BY created_at DESC LIMIT ?",
            [collection_id, limit],
        ).fetchall()
        return [
            {
                "id": str(row[0]),
                "collection_id": str(row[1]),
                "content": str(row[2]),
                "metadata": json.loads(str(row[3] or "{}")),
                "created_at": str(row[4]),
            }
            for row in rows
        ]

    def search(self, collection_id: str, query: str, top_k: int = 5) -> list[VectorSearchResult]:
        collection = self.get_collection(collection_id)
        if not collection:
            return []

        docs = self.get_documents(collection_id, limit=50)
        query_words = set(query.lower().split())

        results: list[VectorSearchResult] = []
        for doc in docs:
            doc_words = set(doc["content"].lower().split())
            overlap = len(query_words & doc_words)
            score = overlap / max(len(query_words | doc_words), 1)
            results.append(
                VectorSearchResult(
                    id=doc["id"],
                    content=doc["content"],
                    score=min(score * 2, 1.0),
                    metadata=doc["metadata"],
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def get_stats(self, collection_id: str) -> CollectionStats | None:
        collection = self.get_collection(collection_id)
        if not collection:
            return None

        count_row = self._conn.execute(
            "SELECT COUNT(*) FROM documents WHERE collection_id = ?",
            [collection_id],
        ).fetchone()
        doc_count = int(count_row[0]) if count_row is not None else 0

        return CollectionStats(
            total_documents=doc_count,
            total_vectors=doc_count,
            index_size_mb=doc_count * 0.001,
            avg_chunk_size=500,
            last_updated=collection.updated_at,
        )

    def _row_to_collection(self, row: tuple[object, ...]) -> VectorCollection:
        return VectorCollection(
            id=str(row[0]),
            name=str(row[1]),
            description=str(row[2] or ""),
            store_type=VectorStoreType(str(row[3])),
            dimension=int(row[4] or 384),  # type: ignore[call-overload]  # DuckDB cursor returns object-typed tuples
            metric=str(row[5] or "cosine"),
            document_count=int(row[6] or 0),  # type: ignore[call-overload]  # DuckDB cursor returns object-typed tuples
            status=CollectionStatus(str(row[7])),
            metadata=json.loads(str(row[8] or "{}")),
            created_at=datetime.fromisoformat(str(row[9])),
            updated_at=datetime.fromisoformat(str(row[10])),
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
