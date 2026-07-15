"""Runtime checks for MovieDEX's nested TMDB transforms."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest
from dataenginex.config import load_config
from dataenginex.data.pipeline.runner import _build_transform_kwargs
from dataenginex.data.transforms import transform_registry

PROJECT_DIR = Path(__file__).parents[2] / "examples" / "movie-dex"


def _record(*, media_type: str = "movie") -> dict[str, Any]:
    title_key = "title" if media_type == "movie" else "name"
    return {
        "id": 101,
        title_key: "Example",
        "external_ids": {"imdb_id": "tt0000101"},
        "credits": {
            "cast": [{"id": 1, "name": "Actor", "character": "Lead"}],
            "crew": [{"id": 2, "name": "Director", "job": "Director"}],
        },
        "keywords": {
            "keywords" if media_type == "movie" else "results": [{"id": 3, "name": "mystery"}]
        },
        "reviews": {
            "results": [
                {"id": "r1", "content": "A" * 60},
                {"id": "r2", "content": "B" * 60},
            ]
        },
        "images": {"posters": [{"file_path": "/poster.jpg"}]},
        "videos": {"results": [{"id": "v1", "name": "Trailer"}]},
        "similar": {"results": [{"id": 102, title_key: "Similar", "vote_average": 8.0}]},
        "watch/providers": {
            "results": {
                "US": {
                    "flatrate": [{"provider_id": 8, "provider_name": "StreamCo"}],
                    "rent": [{"provider_id": 9, "provider_name": "RentCo"}],
                }
            }
        },
    }


def _run_transform(
    conn: duckdb.DuckDBPyConnection,
    pipeline_name: str,
    input_table: str = "input_data",
) -> str:
    config = load_config(PROJECT_DIR / "dex.yaml")
    current = input_table
    for step in config.data.pipelines[pipeline_name].transforms:
        transform = transform_registry.get(step.type)(**_build_transform_kwargs(step))
        current = transform.apply(conn, current)
    return current


@pytest.mark.parametrize(
    ("pipeline_name", "field"),
    [
        ("bronze_tmdb_movie_credits", "credit"),
        ("bronze_tmdb_movie_crew", "credit"),
        ("bronze_tmdb_movie_keywords", "keyword"),
        ("bronze_tmdb_movie_reviews", "review"),
        ("bronze_tmdb_movie_images", "image"),
        ("bronze_tmdb_movie_videos", "video"),
        ("bronze_tmdb_movie_similar", "similar_title"),
        ("bronze_tmdb_tv_credits", "credit"),
        ("bronze_tmdb_tv_crew", "credit"),
        ("bronze_tmdb_tv_keywords", "keyword"),
        ("bronze_tmdb_tv_reviews", "review"),
        ("bronze_tmdb_tv_images", "image"),
        ("bronze_tmdb_tv_videos", "video"),
        ("bronze_tmdb_tv_similar", "similar_title"),
    ],
)
def test_nested_tmdb_explode_pipelines_execute(pipeline_name: str, field: str) -> None:
    media_type = "tv" if "_tv_" in pipeline_name else "movie"
    with duckdb.connect(":memory:") as conn:
        conn.register("raw", pa.Table.from_pylist([_record(media_type=media_type)]))
        conn.execute("CREATE TABLE input_data AS SELECT * FROM raw")
        output = _run_transform(conn, pipeline_name)
        assert conn.execute(f'SELECT "{field}" IS NOT NULL FROM {output}').fetchone() == (True,)


@pytest.mark.parametrize("media_type", ["movie", "tv"])
def test_watch_provider_pipeline_executes(media_type: str) -> None:
    pipeline_name = f"bronze_tmdb_{media_type}_watch_providers"
    with duckdb.connect(":memory:") as conn:
        conn.register("raw", pa.Table.from_pylist([_record(media_type=media_type)]))
        conn.execute("CREATE TABLE input_data AS SELECT * FROM raw")
        output = _run_transform(conn, pipeline_name)
        rows = conn.execute(
            f"SELECT region, provider_name, availability_type FROM {output} "
            "ORDER BY availability_type"
        ).fetchall()
    assert rows == [("US", "StreamCo", "flatrate"), ("US", "RentCo", "rent")]


def test_movie_entity_resolution_uses_nested_external_id_and_match_gate() -> None:
    with duckdb.connect(":memory:") as conn:
        conn.register(
            "raw_titles",
            pa.Table.from_pylist([{"tconst": "tt0000101", "primaryTitle": "Example"}]),
        )
        conn.register("raw_details", pa.Table.from_pylist([_record()]))
        conn.register("raw_ids", pa.Table.from_pylist([{"id": 101}]))
        conn.execute("CREATE TABLE input_data AS SELECT * FROM raw_titles")
        conn.execute("CREATE TABLE bronze_tmdb_movie_details AS SELECT * FROM raw_details")
        conn.execute("CREATE TABLE bronze_tmdb_movie_ids AS SELECT * FROM raw_ids")
        output = _run_transform(conn, "silver_entity_resolution")
        row = conn.execute(
            f"SELECT tconst, tmdb_id, match_confidence, match_rate FROM {output}"
        ).fetchone()
    assert row == ("tt0000101", 101, 1.0, 1.0)


def test_review_similarity_pair_pipeline_executes() -> None:
    with duckdb.connect(":memory:") as conn:
        conn.register("raw", pa.Table.from_pylist([_record()]))
        conn.execute("CREATE TABLE input_data AS SELECT * FROM raw")
        reviews = _run_transform(conn, "bronze_tmdb_movie_reviews")
        conn.execute(f"CREATE TABLE review_input AS SELECT * FROM {reviews}")
        output = _run_transform(conn, "silver_tmdb_review_similarity_pairs", "review_input")
        assert conn.execute(f"SELECT COUNT(*) FROM {output}").fetchone() == (1,)
