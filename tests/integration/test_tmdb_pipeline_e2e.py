"""MovieDEX bronze fixture through real silver and gold pipeline execution."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from dataenginex.config import load_config
from dataenginex.core.exceptions import PipelineStepError
from dataenginex.data.pipeline.runner import PipelineRunner
from dataenginex.lakehouse.storage import DeltaStorage

PROJECT_DIR = Path(__file__).parents[2] / "examples" / "movie-dex"


def _write_bronze_fixture(
    lakehouse: Path,
    *,
    curated_count: int,
    matched_count: int,
) -> None:
    bronze = lakehouse / "bronze"
    bronze.mkdir(parents=True)
    storage = DeltaStorage(base_path=str(bronze), mode="overwrite")
    ids = [{"id": index} for index in range(1, curated_count + 1)]
    titles = [
        {"tconst": f"tt{index:07d}", "primaryTitle": f"Movie {index}"}
        for index in range(1, matched_count + 1)
    ]
    details = [
        {
            "id": index,
            "title": f"Movie {index}",
            "external_ids": {"imdb_id": f"tt{index:07d}"},
        }
        for index in range(1, matched_count + 1)
    ]
    assert storage.write(ids, "bronze_tmdb_movie_ids")
    assert storage.write(titles, "bronze_titles")
    assert storage.write(details, "bronze_tmdb_movie_details")


def _runner(tmp_path: Path) -> PipelineRunner:
    config = load_config(PROJECT_DIR / "dex.yaml")
    return PipelineRunner(
        config,
        data_dir=tmp_path / "lakehouse",
        project_dir=tmp_path,
    )


def test_fixture_runs_bronze_to_silver_to_gold(tmp_path: Path) -> None:
    lakehouse = tmp_path / "lakehouse"
    _write_bronze_fixture(lakehouse, curated_count=1000, matched_count=1000)
    runner = _runner(tmp_path)

    silver = runner.run("silver_entity_resolution")
    gold = runner.run("gold_cross_source_match_confidence")

    assert silver.success and silver.rows_output == 1000
    assert gold.success and gold.rows_output == 1000
    with duckdb.connect(":memory:") as conn:
        row = conn.execute(
            "SELECT COUNT(*), MIN(match_rate), MIN(confidence_tier) "
            f"FROM read_parquet('{lakehouse / 'gold/gold_cross_source_match_confidence.parquet'}')"
        ).fetchone()
    assert row == (1000, 1.0, "HIGH")


def test_entity_resolution_fails_below_match_rate_gate(tmp_path: Path) -> None:
    _write_bronze_fixture(
        tmp_path / "lakehouse",
        curated_count=1000,
        matched_count=799,
    )

    with pytest.raises(PipelineStepError, match="Quality gate failed"):
        _runner(tmp_path).run("silver_entity_resolution")
