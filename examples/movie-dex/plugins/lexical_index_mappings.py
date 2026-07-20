"""MovieDEX Elasticsearch index mappings — movies / reviews / keywords.

Project-local plugin (moviedex-specific, not part of dataenginex core — see
dataenginex/docs/superpowers/specs/2026-07-06-tmdb-data-intelligence-rearchitecture-design.md,
section 3 "Elasticsearch"). Defines the BM25/keyword field mappings for the
three lexical indices declared in dex.yaml under
``ai.retrieval.options.lexical.indices`` (movies, reviews, keywords), and
paired with the dataenginex-core ``ElasticsearchBackend``
(dataenginex.ai.lexical_search) that does the actual indexing/search.

Wiring (production)::

    from elasticsearch import Elasticsearch
    from dataenginex.ai.lexical_search import ElasticsearchBackend

    client = Elasticsearch(["http://elasticsearch:9200"])
    ensure_indices(client)  # creates the 3 indices below if missing
    backend = ElasticsearchBackend(
        hosts=["http://elasticsearch:9200"], index_name="moviedex_movies"
    )
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger()

# English analyzer: lowercases, strips stopwords, stems — standard BM25
# lexical search over free text (title, overview, review body, etc).
_TEXT_FIELD = {"type": "text", "analyzer": "english"}
_KEYWORD_FIELD = {"type": "keyword"}

MOVIES_MAPPING: dict[str, Any] = {
    "properties": {
        "text": _TEXT_FIELD,
        "title": _TEXT_FIELD,
        "overview": _TEXT_FIELD,
        "tagline": _TEXT_FIELD,
        "genres": _KEYWORD_FIELD,
        "release_year": {"type": "integer"},
        "director_name": _KEYWORD_FIELD,
        "imdb_rating": {"type": "float"},
    }
}

REVIEWS_MAPPING: dict[str, Any] = {
    "properties": {
        "text": _TEXT_FIELD,
        "movie_id": _KEYWORD_FIELD,
        "author": _KEYWORD_FIELD,
        "body": _TEXT_FIELD,
        "rating": {"type": "float"},
        "created_at": {"type": "date"},
    }
}

KEYWORDS_MAPPING: dict[str, Any] = {
    "properties": {
        "text": _TEXT_FIELD,
        "movie_id": _KEYWORD_FIELD,
        "keyword": _TEXT_FIELD,
    }
}

# index_name -> mapping, matching dex.yaml's ai.retrieval.options.lexical.indices
INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    "moviedex_movies": MOVIES_MAPPING,
    "moviedex_reviews": REVIEWS_MAPPING,
    "moviedex_keywords": KEYWORDS_MAPPING,
}


def ensure_indices(client: Any) -> None:
    """Create each mapped index on ``client`` if it doesn't already exist.

    Never raises: an unreachable cluster is logged and skipped, matching the
    core ElasticsearchBackend's "never crash the caller" reliability contract.
    """
    for index_name, mapping in INDEX_MAPPINGS.items():
        try:
            if not client.indices.exists(index=index_name):
                client.indices.create(index=index_name, mappings=mapping)
                logger.info("elasticsearch index created", index=index_name)
        except Exception as exc:
            logger.warning("elasticsearch index creation skipped", index=index_name, error=str(exc))


def configure_indices() -> None:
    """Apply MovieDEX mappings at plugin load, with an outage-safe fast fallback."""
    try:
        from elasticsearch import Elasticsearch

        username = os.environ.get("ELASTICSEARCH_USERNAME", "")
        password = os.environ.get("ELASTICSEARCH_PASSWORD", "")
        # ES 9.x python client 9.x sends Accept header with version 9 which ES 9.x rejects.
        # Override to use compatible-with=8 which works with both 8.x and 9.x clusters.
        client = Elasticsearch(
            [os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")],
            basic_auth=(username, password) if username and password else None,
            request_timeout=3,
            headers={"Accept": "application/vnd.elasticsearch+json; compatible-with=8"},
        )
        # Use proper health check endpoint instead of ping (HEAD / returns 400 in ES 8.x/9.x)
        health = client.cluster.health(wait_for_status="yellow", timeout="3s")
        if health["status"] in ("yellow", "green"):
            ensure_indices(client)
        else:
            logger.info(
                "elasticsearch unavailable; index mapping setup deferred", status=health["status"]
            )
    except Exception as exc:
        logger.warning("elasticsearch mapping setup skipped", error=str(exc))


configure_indices()


if __name__ == "__main__":
    # ponytail: minimal smoke self-check, in addition to the pytest suite
    class _FakeIndices:
        def __init__(self) -> None:
            self.created: list[str] = []

        def exists(self, index: str) -> bool:
            return index == "moviedex_reviews"

        def create(self, index: str, mappings: dict[str, Any]) -> None:
            self.created.append(index)

    class _FakeClient:
        def __init__(self) -> None:
            self.indices = _FakeIndices()

    client = _FakeClient()
    ensure_indices(client)
    assert client.indices.created == ["moviedex_movies", "moviedex_keywords"]
    assert set(INDEX_MAPPINGS) == {"moviedex_movies", "moviedex_reviews", "moviedex_keywords"}
    print("lexical index mappings self-check passed")
