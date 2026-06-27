#!/usr/bin/env python3
"""
MovieDEX Setup — download IMDB Non-Commercial datasets and convert to Parquet.

Usage:
    python setup.py              # download all 5 datasets (~1.5 GB compressed)
    python setup.py --quick      # download only titles + ratings (~175 MB)
    #                             # — enough to run pipelines
    python setup.py --skip-download  # convert existing TSV.gz files without re-downloading

IMDB Non-Commercial licence:
    https://developer.imdb.com/non-commercial-datasets/
    Personal and non-commercial use only.
"""

from __future__ import annotations

import argparse
import time
import urllib.request
from pathlib import Path

# ── constants ──────────────────────────────────────────────────────────────────

IMDB_BASE = "https://datasets.imdbws.com"

DATASETS = {
    "title_basics": ("title.basics.tsv.gz", "~150 MB"),
    "title_ratings": ("title.ratings.tsv.gz", "~25 MB"),
    "title_crew": ("title.crew.tsv.gz", "~150 MB"),
    "name_basics": ("name.basics.tsv.gz", "~250 MB"),
    "title_principals": ("title.principals.tsv.gz", "~700 MB"),
}

# Minimum set needed for all pipelines to run
QUICK_SET = {"title_basics", "title_ratings", "title_crew", "name_basics"}

RAW_DIR = Path(__file__).parent / "data" / "raw"


# ── helpers ────────────────────────────────────────────────────────────────────


def _progress(block_count: int, block_size: int, total: int) -> None:
    if total <= 0:
        return
    done = min(block_count * block_size, total)
    pct = done / total * 100
    bar = "█" * int(pct // 4) + "░" * (25 - int(pct // 4))
    mb = done / 1_048_576
    print(f"\r  [{bar}] {pct:5.1f}%  {mb:6.1f} MB", end="", flush=True)


def download(key: str, filename: str, label: str) -> Path:
    url = f"{IMDB_BASE}/{filename}"
    dest = RAW_DIR / filename
    if dest.exists():
        print(f"  ✓  {key:20s} already downloaded — skipping")
        return dest
    print(f"  ↓  {key:20s} {label}")
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress)
        print()
    except Exception as exc:
        print(f"\n  ✗  download failed: {exc}")
        raise
    return dest


def convert_to_parquet(key: str, gz_path: Path) -> Path:
    """Read TSV.gz with DuckDB → write Parquet in the same directory."""
    import duckdb  # noqa: PLC0415  (local import — optional dependency)

    parquet_path = RAW_DIR / f"{key}.parquet"
    if parquet_path.exists():
        print(f"  ✓  {key:20s} parquet already exists — skipping")
        return parquet_path

    print(f"  ⚙  {key:20s} converting TSV.gz → Parquet …", end="", flush=True)
    t0 = time.monotonic()
    with duckdb.connect(":memory:") as conn:
        conn.execute(f"""
            COPY (
                SELECT * FROM read_csv(
                    '{gz_path}',
                    delim      = '\t',
                    header     = true,
                    nullstr    = '\\N',
                    ignore_errors = true
                )
            )
            TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
    rows = (
        duckdb.connect(":memory:")
        .execute(f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')")
        .fetchone()[0]
    )
    elapsed = time.monotonic() - t0
    print(f" done  {rows:>12,} rows  {elapsed:.1f}s")
    return parquet_path


def print_summary(keys: list[str]) -> None:
    print("\n── Parquet summary ────────────────────────────────────────────────")
    try:
        import duckdb  # noqa: PLC0415

        for key in keys:
            p = RAW_DIR / f"{key}.parquet"
            if not p.exists():
                print(f"  {key:22s}  MISSING")
                continue
            size_mb = p.stat().st_size / 1_048_576
            rows = (
                duckdb.connect(":memory:")
                .execute(f"SELECT COUNT(*) FROM read_parquet('{p}')")
                .fetchone()[0]
            )
            print(f"  {key:22s}  {rows:>12,} rows  {size_mb:7.1f} MB")
    except Exception as exc:
        print(f"  (summary failed: {exc})")


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare IMDB datasets for MovieDEX")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Download only titles + ratings + crew + names (~575 MB)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download, convert existing TSV.gz files only",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    target_keys = QUICK_SET if args.quick else set(DATASETS)

    print("── MovieDEX Setup ─────────────────────────────────────────────────")
    print(f"   Destination : {RAW_DIR}")
    print(f"   Mode        : {'quick (no principals)' if args.quick else 'full'}")
    print("   Licence     : IMDB Non-Commercial — personal/research use only")
    print("───────────────────────────────────────────────────────────────────\n")

    processed: list[str] = []

    for key, (filename, label) in DATASETS.items():
        if key not in target_keys:
            continue

        gz_path = RAW_DIR / filename

        # 1. Download
        if not args.skip_download:
            download(key, filename, label)
        elif not gz_path.exists():
            print(f"  ✗  {key:20s} TSV.gz not found at {gz_path} — skipping")
            continue

        # 2. Convert
        try:
            convert_to_parquet(key, gz_path)
            processed.append(key)
        except Exception as exc:
            print(f"  ✗  {key}: conversion failed — {exc}")

    print_summary(processed)

    print("\n── Next steps ─────────────────────────────────────────────────────")
    print("  1. Open MovieDEX in DataEngineX Studio (examples/movie-dex/dex.yaml)")
    print("  2. Go to Compute → Pipelines → run bronze_* pipelines first")
    print("  3. Then run silver_* pipelines (depend on bronze)")
    print("  4. Then run gold_* pipelines (depend on silver)")
    print("  5. Go to ML → Experiments → run rating_predictor experiment")
    print("  6. Go to AI → Playground → chat with movie_recommender agent")
    print("")
    print("  Pro tip: run `dex validate dex.yaml` to verify your config before")
    print("  starting. Pipelines are scheduled daily at 03:00–05:00 UTC.")
    print("───────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
