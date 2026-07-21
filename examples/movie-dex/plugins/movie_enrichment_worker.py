"""Executable RabbitMQ worker for MovieDEX on-demand enrichment."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dataenginex.config import load_config
from dataenginex.core.project_plugins import load_project_plugins
from dataenginex.data.connectors import connector_registry
from dataenginex.orchestration.queue import RabbitMQQueue


def build_worker(project_dir: Path) -> tuple[RabbitMQQueue, Any, Any]:
    load_project_plugins(project_dir)
    config = load_config(project_dir / "dex.yaml")
    tmdb_config = config.data.sources["tmdb_movie_details"]
    connection = dict(tmdb_config.connection)
    id_source_path = Path(str(connection["id_source_path"]))
    if not id_source_path.is_absolute():
        connection["id_source_path"] = str((project_dir / id_source_path).resolve())
    connector = connector_registry.get("tmdb")(**connection)
    connector.connect()

    rabbit_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    parsed = urlparse(rabbit_url)
    queue = RabbitMQQueue(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5672,
        username=parsed.username or "guest",
        password=parsed.password or "guest",
        queue_name="moviedex.movie-enrichment.v1",
        dlq_name="moviedex.movie-enrichment.dlq",
        prefetch_count=10,
    )

    handler_module = __import__("_dex_project_plugin_movie_enrichment_handler")
    handler = handler_module.MovieEnrichmentHandler(
        connector,
        output_path=project_dir / ".dex/lakehouse/bronze/bronze_tmdb_movie_enrichment_events",
        db_url=f"sqlite:///{project_dir / '.dex' / 'moviedex_jobs.db'}",
    )
    return queue, handler, connector


def main() -> None:
    project_dir = Path(os.environ.get("DEX_PROJECT_DIR", Path(__file__).parents[1])).resolve()
    queue, handler, connector = build_worker(project_dir)
    try:
        while True:
            processed = queue.consume(handler)
            if processed == 0:
                time.sleep(1)
    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
