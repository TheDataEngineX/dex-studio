"""MovieDEX GraphQL schema — movies, genre trends, cast, watch providers.

Project-local plugin (moviedex-specific, not part of dataenginex core — see
dataenginex/docs/superpowers/specs/2026-07-06-tmdb-data-intelligence-rearchitecture-design.md,
section 3 "GraphQL"). dataenginex only ships a generic mechanism
(dataenginex.api.graphql.build_schema) that turns a {type_name: table_name}
mapping into read-only Strawberry types — it knows nothing about movies,
cast, or genres. This file supplies moviedex's actual gold/silver table
names to that generic mechanism.

Loaded by dex_studio.app._load_project_graphql_schema() at startup (same
plugins/ convention as tmdb_connector.py / movie_enrichment_handler.py),
which calls build_schema(engine) below and mounts the result at /graphql
if it returns a schema.

Table choices (checked against dex.yaml directly rather than assumed):
- movies:           gold_tmdb_enriched_movies (movie_id) — TMDB-enriched,
                     richer than the IMDB-only gold_top_movies.
- genre trends:      gold_genre_trends (genre_name)
- cast:              silver_unified_cast_crew (resolved_title_id) — unified
                     IMDB+TMDB cast/crew view.
- watch providers:   silver_watch_providers_by_region (tmdb_id) — has a
                     natural per-movie id column; gold_watch_provider_coverage
                     is pre-aggregated by (region, provider) with no such key.
"""

from __future__ import annotations

from typing import Any

from dataenginex.api.graphql import GoldTable
from dataenginex.api.graphql import build_schema as _build_generic_schema

_TABLES: dict[str, str | GoldTable] = {
    "Movie": GoldTable(table="gold_tmdb_enriched_movies", id_column="movie_id"),
    "GenreTrend": GoldTable(table="gold_genre_trends", id_column="genre_name"),
    "CastMember": GoldTable(
        table="silver_unified_cast_crew", id_column="resolved_title_id", layer="silver"
    ),
    "WatchProvider": GoldTable(
        table="silver_watch_providers_by_region", id_column="tmdb_id", layer="silver"
    ),
}


def build_schema(engine: Any) -> Any:
    """Build moviedex's GraphQL schema — called by dex_studio.app at startup."""
    return _build_generic_schema(engine, _TABLES, layer="gold")
