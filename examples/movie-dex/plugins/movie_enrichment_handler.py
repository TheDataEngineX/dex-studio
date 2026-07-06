"""MovieEnrichmentHandler — "enrich movie X" RabbitMQ job handler.

Project-local plugin (moviedex-specific, not part of dataenginex core — see
dataenginex/docs/superpowers/specs/2026-07-06-tmdb-data-intelligence-rearchitecture-design.md).

Consumes ``{"movie_id": <int>}`` messages (published to a
``RabbitMQQueue``, see dataenginex.orchestration.queue.rabbitmq) and
enriches that single movie by calling a connector's ``fetch_one`` — the
exact same TMDB fetch/retry/rate-limit logic ``TmdbConnector.read()`` uses
for the bulk pipeline (dex-studio/examples/movie-dex/plugins/tmdb_connector.py),
reused here rather than duplicated.

Wiring (production)::

    from dataenginex.data.connectors import connector_registry
    connector = connector_registry.get("tmdb")(api_key=..., id_source_path="")
    connector.connect()
    handler = MovieEnrichmentHandler(connector)
    queue.consume(handler)  # RabbitMQQueue.consume(handler: Callable[[dict], bool])
"""

from __future__ import annotations

from typing import Any, Protocol

import structlog

logger = structlog.get_logger()


class _TitleFetcher(Protocol):
    """Duck-typed connector: anything with ``fetch_one(id) -> dict | None``.

    ponytail: typed as a Protocol instead of importing TmdbConnector
    directly — plugins/*.py files are loaded standalone (no package
    __init__, see dataenginex.core.project_plugins.load_project_plugins),
    so a static import here would re-exec tmdb_connector.py's module-level
    ``@connector_registry.decorator("tmdb")`` a second time in the same
    process and raise on duplicate registration. Duck typing plus
    constructor injection sidesteps that entirely — the caller wires up
    the real TmdbConnector instance (see module docstring).
    """

    def fetch_one(self, tmdb_id: int) -> dict[str, Any] | None: ...


class MovieEnrichmentHandler:
    """RabbitMQ job handler: enrich a single movie on demand.

    Args:
        connector: A connected title-fetcher (in production, a connected
            TmdbConnector) used to fetch the single title by ID.
    """

    def __init__(self, connector: _TitleFetcher) -> None:
        self._connector = connector

    def __call__(self, message: dict[str, Any]) -> bool:
        """Handle one ``{"movie_id": <int>}`` message.

        Returns True (ack) on successful enrichment, False (nack) on a
        missing/invalid movie_id or a failed fetch — matches the
        ``Callable[[dict], bool]`` contract RabbitMQQueue.consume expects.
        """
        movie_id = message.get("movie_id")
        if not isinstance(movie_id, int):
            logger.error("enrichment message missing/invalid movie_id", message=message)
            return False

        record = self._connector.fetch_one(movie_id)
        if record is None:
            logger.warning("movie enrichment skipped — fetch failed", movie_id=movie_id)
            return False

        logger.info("movie enriched", movie_id=movie_id)
        return True


if __name__ == "__main__":
    # ponytail: minimal smoke self-check, in addition to the pytest suite
    class _FakeConnector:
        def fetch_one(self, tmdb_id: int) -> dict[str, Any] | None:
            return {"id": tmdb_id} if tmdb_id != 404 else None

    handler = MovieEnrichmentHandler(_FakeConnector())
    assert handler({"movie_id": 42}) is True
    assert handler({"movie_id": 404}) is False
    assert handler({"movie_id": "not-an-int"}) is False
    print("movie enrichment handler self-check passed")
