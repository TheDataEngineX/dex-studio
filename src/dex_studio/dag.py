"""Pipeline dependency graph — pure functions, no I/O."""

from __future__ import annotations

from typing import Any

__all__ = ["build_dag", "downstream_of", "root_pipelines", "topological_order"]


def build_dag(pipelines: dict[str, Any]) -> dict[str, list[str]]:
    """Return {name: [dep1, dep2, ...]} for all pipelines."""
    return {name: list(getattr(cfg, "depends_on", None) or []) for name, cfg in pipelines.items()}


def topological_order(dag: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm. Raises ValueError if a cycle is detected."""
    # remaining[n] = number of unresolved deps for node n
    remaining: dict[str, int] = {n: len(deps) for n, deps in dag.items()}
    # reverse[n] = nodes that depend on n
    reverse: dict[str, list[str]] = {n: [] for n in dag}
    for node, deps in dag.items():
        for d in deps:
            if d in reverse:
                reverse[d].append(node)

    queue = [n for n, cnt in remaining.items() if cnt == 0]
    result: list[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for child in reverse.get(node, []):
            remaining[child] -= 1
            if remaining[child] == 0:
                queue.append(child)

    if len(result) != len(dag):
        raise ValueError("cycle detected in pipeline dependency graph")
    return result


def root_pipelines(dag: dict[str, list[str]]) -> list[str]:
    """Pipelines with no dependencies — triggered by cron schedule."""
    return [name for name, deps in dag.items() if not deps]


def downstream_of(name: str, dag: dict[str, list[str]]) -> list[str]:
    """Direct dependents of `name` (pipelines whose depends_on includes it)."""
    return [n for n, deps in dag.items() if name in deps]
