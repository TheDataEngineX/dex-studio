"""Job vector search using DataEngineX RAG pipeline.

Provides semantic search for job postings using vector embeddings.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

__all__ = ["JobVectorSearch"]


class JobVectorSearch:
    """Semantic job search using DataEngineX vector store."""

    def __init__(self) -> None:
        try:
            from dataenginex.ml.vectorstore import (
                InMemoryBackend,
                SentenceTransformerEmbedder,
            )
        except ImportError as exc:
            raise ImportError(
                "DataEngineX required. Install with: pip install dataenginex[dex]"
            ) from exc

        self._backend = InMemoryBackend(dimension=384)
        self._embedder = SentenceTransformerEmbedder(model="all-MiniLM-L6-v2")
        self._jobs: list[dict[str, Any]] = []

    def index_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """Index job postings for semantic search."""
        from dataenginex.ml.vectorstore import Document

        self._jobs = jobs
        docs = [
            Document(
                text=(
                    f"{job.get('title', '')} | {job.get('company', '')} | "
                    f"{job.get('description', '')}"
                ),
                metadata={"index": i, "job": job},
            )
            for i, job in enumerate(jobs)
        ]
        self._backend.upsert(docs, embedder=self._embedder)
        logger.info("jobs_indexed", count=len(jobs))

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Semantic search for jobs matching the query."""
        results = self._backend.search(query, embedder=self._embedder, top_k=top_k)
        return [self._jobs[r.doc.metadata["index"]] for r in results]

    def similarity_search(self, job_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Find similar jobs based on a job posting text."""
        results = self._backend.search(job_text, embedder=self._embedder, top_k=top_k)
        return [self._jobs[r.doc.metadata["index"]] for r in results]
