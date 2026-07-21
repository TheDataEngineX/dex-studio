"""CompactionEngine must never raw-merge/delete files inside a Delta table
directory (one with a _delta_log/) — doing so desyncs the Delta transaction
log from what's actually on disk, corrupting the table (see bronze_crew
incident: compaction merged two part-files into one and deleted the other,
while _delta_log still referenced both).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dex_studio.compaction import CompactionEngine


def test_skips_delta_table_directory(tmp_path: Path) -> None:
    lakehouse = tmp_path / ".dex" / "lakehouse"
    delta_dir = lakehouse / "bronze" / "bronze_crew"
    delta_dir.mkdir(parents=True)
    (delta_dir / "_delta_log").mkdir()
    (delta_dir / "part-00000-x.parquet").write_bytes(b"x")
    (delta_dir / "part-00001-x.parquet").write_bytes(b"y")

    engine = CompactionEngine(tmp_path, db=MagicMock())
    files = engine._collect_files("bronze_crew")

    assert files == []


def test_still_collects_plain_partition_directory(tmp_path: Path) -> None:
    lakehouse = tmp_path / ".dex" / "lakehouse"
    part_dir = lakehouse / "bronze" / "legacy_pipeline"
    part_dir.mkdir(parents=True)
    (part_dir / "part-0.parquet").write_bytes(b"x")
    (part_dir / "part-1.parquet").write_bytes(b"y")

    engine = CompactionEngine(tmp_path, db=MagicMock())
    files = engine._collect_files("legacy_pipeline")

    assert len(files) == 2


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_skips_delta_table_directory(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_still_collects_plain_partition_directory(Path(tmp))
    print("ok")
