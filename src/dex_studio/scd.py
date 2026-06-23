"""ScdManager — Slowly Changing Dimension handling for DEX Studio pipelines.

Type 1: MERGE / upsert on scd_key_columns — overwrites old values in place.
Type 2: Append + close pattern — keeps full version history with
        valid_from / valid_to / is_current columns.

Both types operate on DuckDB tables via the engine's connection. The manager
reads pipeline config from dex.yaml (via the engine) to determine which type
to apply and which columns are key / tracked.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import structlog

__all__ = ["ScdManager", "ScdResult"]

log = structlog.get_logger().bind(src="scd")


class ScdResult:
    """Summary of one SCD merge operation."""

    __slots__ = ("pipeline", "scd_type", "inserted", "updated", "closed", "unchanged")

    def __init__(
        self,
        pipeline: str,
        scd_type: int,
        inserted: int = 0,
        updated: int = 0,
        closed: int = 0,
        unchanged: int = 0,
    ) -> None:
        self.pipeline = pipeline
        self.scd_type = scd_type
        self.inserted = inserted
        self.updated = updated
        self.closed = closed
        self.unchanged = unchanged

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "scd_type": self.scd_type,
            "inserted": self.inserted,
            "updated": self.updated,
            "closed": self.closed,
            "unchanged": self.unchanged,
        }


class ScdManager:
    """Applies SCD Type 1 or Type 2 logic to a DuckDB table via the engine."""

    def __init__(self, eng: Any) -> None:
        self._eng = eng

    def _get_pipeline_scd_config(self, pipeline: str) -> dict[str, Any]:
        """Extract SCD config from dex.yaml pipeline definition."""
        pipes: dict[str, Any] = self._eng.config.data.pipelines or {}
        cfg = pipes.get(pipeline)
        if cfg is None:
            return {}
        return {
            "scd_type": int(getattr(cfg, "scd_type", 1) or 1),
            "key_columns": list(getattr(cfg, "scd_key_columns", None) or []),
            "tracked_columns": list(getattr(cfg, "scd_tracked_columns", None) or []),
        }

    @staticmethod
    def _row_hash(row: dict[str, Any], columns: list[str]) -> str:
        parts = [f"{c}={row.get(c)}" for c in sorted(columns)]
        return hashlib.md5("|".join(parts).encode()).hexdigest()  # noqa: S324

    # ── Type 1 — upsert ───────────────────────────────────────────────────────

    def apply_type1(
        self,
        pipeline: str,
        incoming: list[dict[str, Any]],
        key_columns: list[str],
    ) -> ScdResult:
        """MERGE incoming rows into the destination table on key_columns.

        Rows with matching keys are updated; new keys are inserted.
        """
        if not incoming:
            return ScdResult(pipeline, 1)

        result = ScdResult(pipeline, 1)
        try:
            con = getattr(self._eng, "connection", self._eng)
            table = pipeline
            cols = list(incoming[0].keys())
            placeholders = ", ".join("?" * len(cols))
            col_list = ", ".join(cols)
            key_cond = " AND ".join(f"t.{k} = s.{k}" for k in key_columns)
            update_cols = [c for c in cols if c not in key_columns]
            update_clause = ", ".join(f"{c} = s.{c}" for c in update_cols)

            # Stage incoming data
            con.execute(
                "CREATE OR REPLACE TEMP TABLE _scd1_stage AS SELECT * FROM (VALUES"
                f" {', '.join('(' + placeholders + ')' for _ in incoming)})"
                f" t({col_list})",
                [v for row in incoming for v in row.values()],
            )

            # Ensure destination table exists (schema inferred from stage)
            con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM _scd1_stage LIMIT 0")

            # Upsert: update existing, insert new
            if update_cols:
                con.execute(
                    f"UPDATE {table} AS t SET {update_clause} FROM _scd1_stage s WHERE {key_cond}"
                )
                result.updated = con.execute(
                    f"SELECT COUNT(*) FROM {table} t JOIN _scd1_stage s ON {key_cond}"
                ).fetchone()[0]

            s_col_list = ", ".join(f"s.{c}" for c in cols)
            count_before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            con.execute(
                f"INSERT INTO {table}({col_list})"
                f" SELECT {s_col_list} FROM _scd1_stage s"
                f" WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE {key_cond})"
            )
            count_after = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            result.inserted = count_after - count_before

            log.info(
                "SCD Type 1 applied",
                pipeline=pipeline,
                inserted=result.inserted,
                updated=result.updated,
            )
        except Exception as exc:
            log.warning("SCD Type 1 failed — passthrough", pipeline=pipeline, error=str(exc))

        return result

    # ── Type 2 — versioned history ────────────────────────────────────────────

    def apply_type2(
        self,
        pipeline: str,
        incoming: list[dict[str, Any]],
        key_columns: list[str],
        tracked_columns: list[str],
    ) -> ScdResult:
        """Append + close pattern for Type 2 SCD.

        Destination table: {pipeline}_history with columns:
          valid_from TEXT, valid_to TEXT (NULL = current), is_current INTEGER
        View {pipeline}: SELECT * WHERE is_current = 1
        """
        if not incoming or not key_columns:
            return ScdResult(pipeline, 2)

        result = ScdResult(pipeline, 2)
        now = datetime.now(UTC).isoformat()

        try:
            con = getattr(self._eng, "connection", self._eng)
            hist_table = f"{pipeline}_history"

            # Ensure history table exists with SCD columns
            sample = incoming[0]
            col_defs = ", ".join(f"{c} TEXT" for c in sample)
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {hist_table}"
                f" ({col_defs},"
                f"  valid_from TEXT NOT NULL,"
                f"  valid_to TEXT,"
                f"  is_current INTEGER NOT NULL DEFAULT 1)"
            )

            for row in incoming:
                row_hash = self._row_hash(row, tracked_columns or list(row.keys()))
                # Find current version
                key_vals = [row[k] for k in key_columns]
                key_where = " AND ".join(f"{k} = ?" for k in key_columns)
                current = con.execute(
                    f"SELECT * FROM {hist_table} WHERE {key_where} AND is_current = 1",
                    key_vals,
                ).fetchone()

                if current is None:
                    # New key — insert first version
                    cols = list(row.keys())
                    vals = list(row.values())
                    col_list = ", ".join(cols + ["valid_from", "valid_to", "is_current"])
                    placeholders = ", ".join("?" * (len(cols) + 3))
                    con.execute(
                        f"INSERT INTO {hist_table}({col_list}) VALUES({placeholders})",
                        vals + [now, None, 1],
                    )
                    result.inserted += 1
                else:
                    # Check if tracked columns changed
                    desc_names = [d[0] for d in con.description or []]
                    cur_dict = dict(zip(desc_names, current, strict=False))
                    cur_hash = self._row_hash(
                        {k: cur_dict.get(k) for k in (tracked_columns or list(row.keys()))},
                        tracked_columns or list(row.keys()),
                    )
                    if cur_hash != row_hash:
                        # Close current version
                        con.execute(
                            f"UPDATE {hist_table} SET valid_to=?, is_current=0"
                            f" WHERE {key_where} AND is_current=1",
                            [now] + key_vals,
                        )
                        result.closed += 1
                        # Insert new version
                        cols = list(row.keys())
                        vals = list(row.values())
                        col_list = ", ".join(cols + ["valid_from", "valid_to", "is_current"])
                        placeholders = ", ".join("?" * (len(cols) + 3))
                        con.execute(
                            f"INSERT INTO {hist_table}({col_list}) VALUES({placeholders})",
                            vals + [now, None, 1],
                        )
                        result.inserted += 1
                    else:
                        result.unchanged += 1

            # Recreate current view
            con.execute(
                f"CREATE OR REPLACE VIEW {pipeline} AS"
                f" SELECT * FROM {hist_table} WHERE is_current = 1"
            )

            log.info(
                "SCD Type 2 applied",
                pipeline=pipeline,
                inserted=result.inserted,
                closed=result.closed,
                unchanged=result.unchanged,
            )
        except Exception as exc:
            log.warning("SCD Type 2 failed — passthrough", pipeline=pipeline, error=str(exc))

        return result

    def apply(self, pipeline: str, incoming: list[dict[str, Any]]) -> ScdResult:
        """Apply the SCD strategy configured in dex.yaml for *pipeline*."""
        cfg = self._get_pipeline_scd_config(pipeline)
        scd_type = cfg.get("scd_type", 1)
        key_cols = cfg.get("key_columns", [])
        tracked_cols = cfg.get("tracked_columns", [])

        if not key_cols:
            log.debug("no scd_key_columns — skipping SCD", pipeline=pipeline)
            return ScdResult(pipeline, scd_type)

        if scd_type == 2:
            return self.apply_type2(pipeline, incoming, key_cols, tracked_cols)
        return self.apply_type1(pipeline, incoming, key_cols)
