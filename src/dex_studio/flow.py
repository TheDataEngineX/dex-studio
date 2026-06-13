"""Flow-canvas model: turns a pipeline config (+ optional per-stage row counts)
into an ordered list of nodes — source → transforms → destination — for the
Azure-Data-Factory-style Transforms page."""

from __future__ import annotations

from typing import Any


def _summary(step: Any) -> str:
    """One-line human label for a transform step."""
    if getattr(step, "condition", None):
        return str(step.condition)
    if getattr(step, "sql", None):
        return str(step.sql).strip().splitlines()[0]
    key = getattr(step, "key", None)
    if key:
        return f"key: {key if isinstance(key, str) else ', '.join(key)}"
    name = getattr(step, "name", None)
    if name:
        return f"{name} = {getattr(step, 'expression', '') or ''}"
    return str(getattr(step, "type", ""))


def build_nodes(cfg: Any, stages: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Build flow nodes. *stages* (from engine.preview_flow) supplies row counts
    aligned as [source, *transforms, destination]; omit it for a fast count-less render."""
    transforms = getattr(cfg, "transforms", None) or []

    def rows_at(i: int) -> int | None:
        return stages[i]["rows"] if stages and i < len(stages) else None

    def est_at(i: int) -> bool:
        return bool(stages[i].get("estimated")) if stages and i < len(stages) else False

    nodes: list[dict[str, Any]] = [
        {
            "kind": "source",
            "type": "source",
            "label": str(getattr(cfg, "source", "") or "source"),
            "rows": rows_at(0),
            "estimated": False,
            "index": None,
        },
    ]
    for i, step in enumerate(transforms):
        nodes.append(
            {
                "kind": "transform",
                "type": str(getattr(step, "type", "")),
                "label": _summary(step),
                "rows": rows_at(i + 1),
                "estimated": est_at(i + 1),
                "index": i,
            }
        )
    last = len(transforms) + 1
    nodes.append(
        {
            "kind": "destination",
            "type": "destination",
            "label": str(getattr(cfg, "destination", "") or "output"),
            "rows": rows_at(last),
            "estimated": est_at(last),
            "index": None,
        }
    )
    return nodes
