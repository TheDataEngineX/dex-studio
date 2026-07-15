"""Pipeline definition domain layer — DAG model over Node/Edge DB rows.

Owns the graph shape (topological ordering, cycle detection) and the
dex.yaml import/export bridge. Execution (locking, retries, scheduling)
stays in scheduler.py/jobs.py — this module only knows about structure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from dex_studio.studio_db import PgStudioDb, StudioDb

__all__ = [
    "PipelineDefinitionStore",
    "PipelineEdge",
    "PipelineGraph",
    "PipelineNode",
]


@dataclass(frozen=True, slots=True)
class PipelineNode:
    id: str
    kind: str
    transform_type: str
    config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PipelineEdge:
    id: str
    from_node_id: str
    to_node_id: str


@dataclass(slots=True)
class PipelineGraph:
    pipeline_id: str
    name: str
    nodes: list[PipelineNode] = field(default_factory=list)
    edges: list[PipelineEdge] = field(default_factory=list)


class PipelineDefinitionStore:
    """Reads/writes pipeline DAGs via a StudioDb/PgStudioDb backend."""

    def __init__(self, db: StudioDb | PgStudioDb | None) -> None:
        self._db = db

    def get_graph(self, project_id: str, name: str) -> PipelineGraph | None:
        assert self._db is not None, "get_graph requires a db backend"
        pdef = self._db.get_pipeline_def(project_id, name)
        if pdef is None:
            return None
        nodes = [
            PipelineNode(
                id=n["id"],
                kind=n["kind"],
                transform_type=n["transform_type"],
                config=n["config"],
            )
            for n in self._db.list_nodes(pdef["id"])
        ]
        edges = [
            PipelineEdge(id=e["id"], from_node_id=e["from_node_id"], to_node_id=e["to_node_id"])
            for e in self._db.list_edges(pdef["id"])
        ]
        return PipelineGraph(pipeline_id=pdef["id"], name=name, nodes=nodes, edges=edges)

    def topological_order(self, graph: PipelineGraph) -> list[PipelineNode]:
        """Kahn's algorithm. Raises ValueError if the graph has a cycle."""
        nodes_by_id = {n.id: n for n in graph.nodes}
        in_degree = dict.fromkeys(nodes_by_id, 0)
        outgoing: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
        for edge in graph.edges:
            outgoing[edge.from_node_id].append(edge.to_node_id)
            in_degree[edge.to_node_id] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        ordered: list[PipelineNode] = []
        while queue:
            nid = queue.popleft()
            ordered.append(nodes_by_id[nid])
            for target in outgoing[nid]:
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)

        if len(ordered) != len(graph.nodes):
            raise ValueError(f"pipeline '{graph.name}' has a cycle in its node graph")
        return ordered

    def export_to_yaml_steps(self, graph: PipelineGraph) -> list[dict[str, Any]]:
        """Linear pipelines only — raises ValueError on any branching node.

        Branching export needs a dex.yaml step-type extension that doesn't
        exist yet (see design spec's Open Items); this method intentionally
        refuses to silently drop branches rather than exporting wrong data.
        """
        outgoing_count: dict[str, int] = dict.fromkeys((n.id for n in graph.nodes), 0)
        incoming_count: dict[str, int] = dict.fromkeys((n.id for n in graph.nodes), 0)
        for edge in graph.edges:
            outgoing_count[edge.from_node_id] += 1
            incoming_count[edge.to_node_id] += 1

        if any(c > 1 for c in outgoing_count.values()) or any(
            c > 1 for c in incoming_count.values()
        ):
            raise ValueError(
                f"pipeline '{graph.name}' has branching nodes — YAML export only"
                " supports linear pipelines"
            )

        ordered = self.topological_order(graph)
        return [{"type": n.transform_type, **n.config} for n in ordered if n.kind == "transform"]

    def import_from_yaml_steps(
        self,
        project_id: str,
        pipeline_name: str,
        source: str,
        destination: str,
        schedule: str,
        depends_on: list[str],
        steps: list[dict[str, Any]],
    ) -> str:
        """Idempotent and all-or-nothing: safe to call repeatedly for the same
        pipeline name.

        Existing pipeline_defs/nodes/edges for this (project_id, name) are
        reused as-is — this never overwrites DB rows that already exist,
        per the migration-path decision in the design spec.

        If any node/edge write fails partway through, the pipeline_defs row
        and any nodes/edges already written for it are deleted so a retry
        starts clean rather than getting stuck on a truncated graph (each
        DB write commits independently, so this can't be a real transaction —
        see StudioDb.delete_pipeline_def).
        """
        assert self._db is not None, "import_from_yaml_steps requires a db backend"

        existing = self._db.get_pipeline_def(project_id, pipeline_name)
        if existing is not None:
            return cast(str, existing["id"])

        pipeline_id = self._db.create_pipeline_def(
            project_id, pipeline_name, schedule=schedule, depends_on=depends_on
        )

        try:
            source_node_id = f"{pipeline_id}-src"
            self._db.upsert_node(pipeline_id, source_node_id, "source", "", {"table": source})

            prev_node_id = source_node_id
            for i, step in enumerate(steps):
                step_kind = str(step.get("type", "transform"))
                node_id = f"{pipeline_id}-step{i}"
                config = {k: v for k, v in step.items() if k != "type"}
                self._db.upsert_node(pipeline_id, node_id, "transform", step_kind, config)
                edge_id = f"{pipeline_id}-e{i}"
                self._db.upsert_edge(pipeline_id, edge_id, prev_node_id, node_id)
                prev_node_id = node_id

            sink_node_id = f"{pipeline_id}-sink"
            self._db.upsert_node(pipeline_id, sink_node_id, "sink", "", {"table": destination})
            self._db.upsert_edge(pipeline_id, f"{pipeline_id}-e-sink", prev_node_id, sink_node_id)
        except Exception:
            self._db.delete_pipeline_def(pipeline_id)
            raise

        return pipeline_id
