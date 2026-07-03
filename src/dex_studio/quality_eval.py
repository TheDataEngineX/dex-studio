"""Evaluate per-column quality rules against a pipeline's actual lakehouse data.

Rules are configured through the pipeline quality tab UI and stored via
studio_db's quality_rules table. Previously nothing ever ran them against real
data — "Run checks" was a no-op redirect and every rule showed as passing
regardless of the underlying data. This module does the actual evaluation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
import structlog

log = structlog.get_logger().bind(src="quality_eval")

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def _sanitize(name: str) -> str:
    return _UNSAFE_NAME_CHARS.sub("", name)[:128]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def find_parquet_path(project_dir: Path, pipeline: str) -> Path | None:
    root = project_dir / ".dex" / "lakehouse"
    safe = _sanitize(pipeline)
    for layer in ("bronze", "silver", "gold"):
        p = root / layer / f"{safe}.parquet"
        if p.exists():
            return p
    return None


def _check_null(con: Any, src: str, col: str, config: dict[str, Any]) -> bool:
    n = con.execute(f"SELECT COUNT(*) FROM {src} WHERE {col} IS NULL").fetchone()[0]
    return bool(n == 0)


def _check_unique(con: Any, src: str, col: str, config: dict[str, Any]) -> bool:
    q = f"SELECT COUNT(*), COUNT(DISTINCT {col}) FROM {src}"
    total, distinct = con.execute(q).fetchone()
    return bool(total == distinct)


def _check_range(con: Any, src: str, col: str, config: dict[str, Any]) -> bool:
    lo, hi = config.get("min"), config.get("max")
    conds, params = [], []
    if lo not in (None, ""):
        conds.append(f"{col} < ?")
        params.append(lo)
    if hi not in (None, ""):
        conds.append(f"{col} > ?")
        params.append(hi)
    if not conds:
        return True
    q = f"SELECT COUNT(*) FROM {src} WHERE {' OR '.join(conds)}"
    n = con.execute(q, params).fetchone()[0]
    return bool(n == 0)


def _check_enum(con: Any, src: str, col: str, config: dict[str, Any]) -> bool:
    allowed = config.get("allowed") or []
    if not allowed:
        return True
    placeholders = ",".join("?" for _ in allowed)
    q = f"SELECT COUNT(*) FROM {src} WHERE {col} IS NOT NULL AND {col} NOT IN ({placeholders})"
    n = con.execute(q, list(allowed)).fetchone()[0]
    return bool(n == 0)


def _check_pattern(con: Any, src: str, col: str, config: dict[str, Any]) -> bool:
    pattern = config.get("pattern") or ""
    if not pattern:
        return True
    q = f"SELECT COUNT(*) FROM {src} WHERE {col} IS NOT NULL AND NOT regexp_matches({col}, ?)"
    n = con.execute(q, [pattern]).fetchone()[0]
    return bool(n == 0)


def _check_fk(con: Any, src: str, col: str, config: dict[str, Any], table_path: Path) -> bool:
    ref_table, ref_col = config.get("ref_table"), config.get("ref_col")
    if not ref_table or not ref_col:
        return True
    ref_path = None
    for layer in ("gold", "silver", "bronze"):
        candidate = table_path.parent.parent / layer / f"{_sanitize(ref_table)}.parquet"
        if candidate.exists():
            ref_path = candidate
            break
    if ref_path is None:
        raise ValueError(f"FK reference table '{ref_table}' not found in lakehouse")
    ref_col_ident = _quote_ident(ref_col)
    q = (
        f"SELECT COUNT(*) FROM {src} WHERE {col} IS NOT NULL AND {col} NOT IN "
        f"(SELECT {ref_col_ident} FROM read_parquet('{ref_path}'))"
    )
    n = con.execute(q).fetchone()[0]
    return bool(n == 0)


def _check_expr(con: Any, src: str, col: str, config: dict[str, Any]) -> bool:
    expr = config.get("expr") or ""
    if not expr:
        return True
    n = con.execute(f"SELECT COUNT(*) FROM {src} WHERE NOT ({expr})").fetchone()[0]
    return bool(n == 0)


def _check_type(con: Any, src: str, col_name: str, config: dict[str, Any]) -> bool:
    # The add-rule UI doesn't currently collect an expected type, so this can
    # only verify the column is still present in the current schema.
    cols = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()]
    return col_name in cols


_RULE_CHECKS: dict[str, Any] = {
    "NULL": _check_null,
    "UNIQUE": _check_unique,
    "RANGE": _check_range,
    "ENUM": _check_enum,
    "PATTERN": _check_pattern,
    "EXPR": _check_expr,
    "TYPE": _check_type,
}


def evaluate_rule(
    con: duckdb.DuckDBPyConnection,
    table_path: Path,
    col_name: str,
    rule_type: str,
    config: dict[str, Any],
) -> bool:
    """Return True if the rule passes against current data.

    Raises on a query/config error (bad regex, missing FK table, unknown rule
    type, ...) so the caller can record that as a distinct failure reason
    instead of a silent pass.
    """
    src = f"read_parquet('{table_path}')"
    col = _quote_ident(col_name)

    if rule_type == "FK":
        return _check_fk(con, src, col, config, table_path)

    check = _RULE_CHECKS.get(rule_type)
    if check is None:
        raise ValueError(f"unknown rule_type: {rule_type}")
    return bool(check(con, src, col if rule_type != "TYPE" else col_name, config))


def run_quality_rules(
    project_dir: Path, pipeline: str, rules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Evaluate every enabled rule for a pipeline against its current data.

    Returns one {id, passed, error} entry per rule. `error` is set (and
    `passed` forced False) when the rule itself couldn't be evaluated.
    """
    path = find_parquet_path(project_dir, pipeline)
    if path is None:
        no_data_error = "no data file found for pipeline"
        return [{"id": r["id"], "passed": False, "error": no_data_error} for r in rules]

    results: list[dict[str, Any]] = []
    with duckdb.connect() as con:
        for r in rules:
            if not r.get("enabled", True):
                continue
            try:
                config = r.get("config") or {}
                passed = evaluate_rule(con, path, r["col_name"], r["rule_type"], config)
                results.append({"id": r["id"], "passed": passed, "error": None})
            except Exception as exc:
                log.warning(
                    "quality rule evaluation failed",
                    rule_id=r["id"],
                    pipeline=pipeline,
                    rule_type=r.get("rule_type"),
                    error=str(exc),
                )
                results.append({"id": r["id"], "passed": False, "error": str(exc)})
    return results
