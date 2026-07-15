"""Tests for the pipeline definition domain layer."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from dex_studio.pipeline_definition import (
    PipelineDefinitionStore,
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
)
from dex_studio.studio_db import StudioDb


def _graph(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> PipelineGraph:
    return PipelineGraph(pipeline_id="p1", name="test", nodes=nodes, edges=edges)


class TestTopologicalOrder:
    def test_linear_chain(self) -> None:
        nodes = [
            PipelineNode(id="a", kind="source", transform_type="", config={}),
            PipelineNode(id="b", kind="transform", transform_type="filter", config={}),
            PipelineNode(id="c", kind="sink", transform_type="", config={}),
        ]
        edges = [
            PipelineEdge(id="e1", from_node_id="a", to_node_id="b"),
            PipelineEdge(id="e2", from_node_id="b", to_node_id="c"),
        ]
        store = PipelineDefinitionStore(db=None)  # topological_order doesn't touch db
        order = [n.id for n in store.topological_order(_graph(nodes, edges))]
        assert order == ["a", "b", "c"]

    def test_fan_out_fan_in(self) -> None:
        nodes = [
            PipelineNode(id="src", kind="source", transform_type="", config={}),
            PipelineNode(id="branch1", kind="transform", transform_type="filter", config={}),
            PipelineNode(id="branch2", kind="transform", transform_type="derive", config={}),
            PipelineNode(id="join", kind="transform", transform_type="join", config={}),
        ]
        edges = [
            PipelineEdge(id="e1", from_node_id="src", to_node_id="branch1"),
            PipelineEdge(id="e2", from_node_id="src", to_node_id="branch2"),
            PipelineEdge(id="e3", from_node_id="branch1", to_node_id="join"),
            PipelineEdge(id="e4", from_node_id="branch2", to_node_id="join"),
        ]
        store = PipelineDefinitionStore(db=None)
        order = [n.id for n in store.topological_order(_graph(nodes, edges))]
        assert order.index("src") < order.index("branch1")
        assert order.index("src") < order.index("branch2")
        assert order.index("branch1") < order.index("join")
        assert order.index("branch2") < order.index("join")

    def test_cycle_raises(self) -> None:
        nodes = [
            PipelineNode(id="a", kind="transform", transform_type="filter", config={}),
            PipelineNode(id="b", kind="transform", transform_type="filter", config={}),
        ]
        edges = [
            PipelineEdge(id="e1", from_node_id="a", to_node_id="b"),
            PipelineEdge(id="e2", from_node_id="b", to_node_id="a"),
        ]
        store = PipelineDefinitionStore(db=None)
        with pytest.raises(ValueError, match="cycle"):
            store.topological_order(_graph(nodes, edges))


class TestYamlImport:
    def test_import_creates_source_steps_sink_chain(self) -> None:
        with TemporaryDirectory() as tmp:
            db = StudioDb(Path(tmp) / "studio.db")
            store = PipelineDefinitionStore(db)

            pipeline_id = store.import_from_yaml_steps(
                project_id="proj1",
                pipeline_name="clean_orders",
                source="raw_orders",
                destination="silver_orders",
                schedule="0 * * * *",
                depends_on=[],
                steps=[
                    {"type": "filter", "condition": "amount > 0"},
                    {"type": "deduplicate", "key": ["order_id"]},
                ],
            )

            graph = store.get_graph("proj1", "clean_orders")
            assert graph is not None
            assert graph.pipeline_id == pipeline_id
            kinds = [n.kind for n in graph.nodes]
            assert kinds == ["source", "transform", "transform", "sink"]
            order = [n.id for n in store.topological_order(graph)]
            assert len(order) == 4  # linear chain, no cycle

    def test_import_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            db = StudioDb(Path(tmp) / "studio.db")
            store = PipelineDefinitionStore(db)

            id1 = store.import_from_yaml_steps(
                project_id="proj1",
                pipeline_name="p",
                source="src",
                destination="dst",
                schedule="",
                depends_on=[],
                steps=[{"type": "filter", "condition": "x > 0"}],
            )
            id2 = store.import_from_yaml_steps(
                project_id="proj1",
                pipeline_name="p",
                source="src",
                destination="dst",
                schedule="",
                depends_on=[],
                steps=[{"type": "filter", "condition": "x > 0"}],
            )

            assert id1 == id2
            graph = store.get_graph("proj1", "p")
            assert graph is not None
            assert len(graph.nodes) == 3  # source, filter, sink — not duplicated

    def test_import_crash_mid_write_leaves_no_partial_state(self) -> None:
        """A crash after the source node lands but before the sink must not
        leave a permanently-truncated pipeline_defs row — see the Important
        finding on import_from_yaml_steps: the idempotency check in step 1
        would otherwise early-return on the broken row forever.
        """
        with TemporaryDirectory() as tmp:
            db = StudioDb(Path(tmp) / "studio.db")
            store = PipelineDefinitionStore(db)

            real_upsert_edge = db.upsert_edge
            calls = {"n": 0}

            def flaky_upsert_edge(*args: object, **kwargs: object) -> None:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("simulated crash mid-import")
                real_upsert_edge(*args, **kwargs)  # type: ignore[arg-type]

            db.upsert_edge = flaky_upsert_edge  # type: ignore[method-assign]

            with pytest.raises(RuntimeError, match="simulated crash mid-import"):
                store.import_from_yaml_steps(
                    project_id="proj1",
                    pipeline_name="p",
                    source="src",
                    destination="dst",
                    schedule="",
                    depends_on=[],
                    steps=[{"type": "filter", "condition": "x > 0"}],
                )

            # No permanent broken state: the pipeline_defs row (and any
            # nodes/edges written before the crash) must be gone.
            assert db.get_pipeline_def("proj1", "p") is None

            db.upsert_edge = real_upsert_edge  # type: ignore[method-assign]

            # A retry must succeed and produce a complete graph.
            pipeline_id = store.import_from_yaml_steps(
                project_id="proj1",
                pipeline_name="p",
                source="src",
                destination="dst",
                schedule="",
                depends_on=[],
                steps=[{"type": "filter", "condition": "x > 0"}],
            )
            graph = store.get_graph("proj1", "p")
            assert graph is not None
            assert graph.pipeline_id == pipeline_id
            assert len(graph.nodes) == 3
            assert len(graph.edges) == 2
            kinds = [n.kind for n in graph.nodes]
            assert kinds == ["source", "transform", "sink"]


class TestYamlExport:
    def test_export_linear_pipeline(self) -> None:
        nodes = [
            PipelineNode(id="src", kind="source", transform_type="", config={"table": "raw"}),
            PipelineNode(
                id="n1",
                kind="transform",
                transform_type="filter",
                config={"condition": "x > 0"},
            ),
            PipelineNode(
                id="n2",
                kind="transform",
                transform_type="deduplicate",
                config={"key": ["id"]},
            ),
            PipelineNode(id="sink", kind="sink", transform_type="", config={"table": "clean"}),
        ]
        edges = [
            PipelineEdge(id="e1", from_node_id="src", to_node_id="n1"),
            PipelineEdge(id="e2", from_node_id="n1", to_node_id="n2"),
            PipelineEdge(id="e3", from_node_id="n2", to_node_id="sink"),
        ]
        graph = _graph(nodes, edges)
        store = PipelineDefinitionStore(db=None)

        steps = store.export_to_yaml_steps(graph)

        assert steps == [
            {"type": "filter", "condition": "x > 0"},
            {"type": "deduplicate", "key": ["id"]},
        ]

    def test_export_branching_pipeline_raises(self) -> None:
        nodes = [
            PipelineNode(id="src", kind="source", transform_type="", config={}),
            PipelineNode(id="b1", kind="transform", transform_type="filter", config={}),
            PipelineNode(id="b2", kind="transform", transform_type="derive", config={}),
        ]
        edges = [
            PipelineEdge(id="e1", from_node_id="src", to_node_id="b1"),
            PipelineEdge(id="e2", from_node_id="src", to_node_id="b2"),
        ]
        graph = _graph(nodes, edges)
        store = PipelineDefinitionStore(db=None)

        with pytest.raises(ValueError, match="branching"):
            store.export_to_yaml_steps(graph)
