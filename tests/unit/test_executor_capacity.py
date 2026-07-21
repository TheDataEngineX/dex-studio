"""_EXECUTOR must have enough real worker threads to match any reasonable
max_concurrent_pipelines config. Previously hardcoded to max_workers=1, so
_start_next_queued could mark N pipelines "running" in the DB while only one
actually executed — the rest sat idle in the executor's internal queue,
serialized behind whichever earlier submission held the one thread.
"""

from __future__ import annotations

from dex_studio import jobs


def test_executor_supports_real_concurrency() -> None:
    assert jobs._EXECUTOR._max_workers >= 8


if __name__ == "__main__":
    test_executor_supports_real_concurrency()
    print("ok")
