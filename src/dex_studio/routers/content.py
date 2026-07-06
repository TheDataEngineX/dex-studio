"""MovieDEX domain explorer: recommendations, providers, and match confidence."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from dataenginex.orchestration.queue import RabbitMQQueue
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dex_studio.routers._deps import AdminDep, ReadDep, base_ctx, render
from dex_studio.tools.builtins import _tool_query

router = APIRouter()


def _rows(sql: str) -> list[dict[str, Any]]:
    try:
        result = _tool_query(sql)
        if isinstance(result, list):
            return [dict(row) for row in result if isinstance(row, dict)]
        if hasattr(result, "to_dict"):
            return list(result.to_dict(orient="records"))
    except Exception:
        pass
    return []


@router.get("/explorer", response_class=HTMLResponse)
def explorer(request: Request, eng: ReadDep, movie_id: int | None = None) -> HTMLResponse:
    movies = _rows(
        "SELECT tmdb_id, title, release_year, imdb_rating "
        "FROM gold_tmdb_enriched_movies ORDER BY imdb_rating DESC NULLS LAST LIMIT 100"
    )
    selected_id = movie_id or (int(movies[0]["tmdb_id"]) if movies else None)
    selected = next((movie for movie in movies if int(movie["tmdb_id"]) == selected_id), None)

    tmdb_similar: list[dict[str, Any]] = []
    own_similar: list[dict[str, Any]] = []
    providers: list[dict[str, Any]] = []
    confidence: list[dict[str, Any]] = []
    if selected_id is not None:
        tmdb_similar = _rows(
            "SELECT similar_title.id AS tmdb_id, similar_title.title AS title, "
            "similar_title.vote_average AS score "
            f"FROM bronze_tmdb_movie_similar WHERE id = {selected_id} "
            "ORDER BY score DESC NULLS LAST LIMIT 10"
        )
        own_similar = _rows(
            "WITH selected AS ("
            " SELECT f.* FROM gold_movie_features f"
            " INNER JOIN gold_tmdb_enriched_movies m ON f.movie_id = m.movie_id"
            f" WHERE m.tmdb_id = {selected_id} LIMIT 1"
            "), scored AS ("
            " SELECT f.movie_id, f.title,"
            " SQRT("
            " POW(f.year_norm-s.year_norm,2)+POW(f.director_avg_rating-s.director_avg_rating,2)+"
            " POW(f.g_action-s.g_action,2)+POW(f.g_drama-s.g_drama,2)+"
            " POW(f.g_comedy-s.g_comedy,2)+POW(f.g_thriller-s.g_thriller,2)+"
            " POW(f.g_crime-s.g_crime,2)+POW(f.g_romance-s.g_romance,2)+"
            " POW(f.g_scifi-s.g_scifi,2)+POW(f.g_horror-s.g_horror,2)+"
            " POW(f.g_adventure-s.g_adventure,2)+POW(f.g_animation-s.g_animation,2)+"
            " POW(f.g_fantasy-s.g_fantasy,2)+POW(f.g_mystery-s.g_mystery,2)"
            " ) AS distance"
            " FROM gold_movie_features f CROSS JOIN selected s"
            " WHERE f.movie_id <> s.movie_id"
            ") SELECT movie_id, title, ROUND(1.0/(1.0+distance),4) AS score"
            " FROM scored ORDER BY distance LIMIT 10"
        )
        providers = _rows(
            "SELECT region, provider_name, availability_type "
            "FROM silver_watch_providers_by_region "
            f"WHERE media_type = 'movie' AND tmdb_id = {selected_id} "
            "ORDER BY region, provider_name"
        )
        confidence = _rows(
            "SELECT tconst, tmdb_id, match_confidence, match_rate, confidence_tier "
            "FROM gold_cross_source_match_confidence "
            f"WHERE tmdb_id = {selected_id}"
        )

    ctx = {
        **base_ctx(request),
        "movies": movies,
        "selected_id": selected_id,
        "selected": selected,
        "tmdb_similar": tmdb_similar,
        "own_similar": own_similar,
        "providers": providers,
        "confidence": confidence,
    }
    return render(request, "content/explorer.html", ctx)


class EnrichmentRequest(BaseModel):
    movie_id: int
    priority: int = 5


@router.post("/admin/enrich")
def enqueue_enrichment(payload: EnrichmentRequest, _claims: AdminDep) -> dict[str, Any]:
    """JWT-protected admin mutation that queues one idempotent enrichment job."""
    parsed = urlparse(os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"))
    queue = RabbitMQQueue(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5672,
        username=parsed.username or "guest",
        password=parsed.password or "guest",
        queue_name="moviedex.movie-enrichment.v1",
        dlq_name="moviedex.movie-enrichment.dlq",
        timeout_seconds=3,
    )
    job_id = f"tmdb-movie-{payload.movie_id}"
    queue.publish(
        {"job_id": job_id, "movie_id": payload.movie_id},
        priority=max(0, min(payload.priority, 9)),
    )
    return {"status": "queued", "job_id": job_id}
