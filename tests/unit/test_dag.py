from __future__ import annotations

import pytest
from dataenginex.data.pipeline.dag import (
    build_dag,
    downstream_of,
    root_pipelines,
    topological_order,
)

from dex_studio.dag import build_dag, downstream_of, root_pipelines, topological_order


def _cfg(**kwargs: list[str]):
    """Minimal pipeline config stub with depends_on."""

    class _Stub:
        depends_on = kwargs.get("depends_on", [])

    return _Stub()


def test_build_dag_empty():
    assert build_dag({}) == {}


def test_build_dag_no_deps():
    pipes = {"bronze": _cfg(), "silver": _cfg()}
    dag = build_dag(pipes)
    assert dag == {"bronze": [], "silver": []}


def test_build_dag_with_deps():
    pipes = {
        "bronze": _cfg(),
        "silver": _cfg(depends_on=["bronze"]),
        "gold": _cfg(depends_on=["silver"]),
    }
    dag = build_dag(pipes)
    assert dag["silver"] == ["bronze"]
    assert dag["gold"] == ["silver"]
    assert dag["bronze"] == []


def test_topological_order_flat():
    dag = {"a": [], "b": [], "c": []}
    order = topological_order(dag)
    assert set(order) == {"a", "b", "c"}


def test_topological_order_chain():
    dag = {"bronze": [], "silver": ["bronze"], "gold": ["silver"]}
    order = topological_order(dag)
    assert order.index("bronze") < order.index("silver")
    assert order.index("silver") < order.index("gold")


def test_topological_order_cycle_raises():
    dag = {"a": ["b"], "b": ["a"]}
    with pytest.raises(ValueError, match="cycle"):
        topological_order(dag)


def test_root_pipelines_all_independent():
    dag = {"a": [], "b": [], "c": []}
    assert set(root_pipelines(dag)) == {"a", "b", "c"}


def test_root_pipelines_only_roots():
    dag = {"bronze": [], "silver": ["bronze"], "gold": ["silver"]}
    assert root_pipelines(dag) == ["bronze"]


def test_downstream_of_direct():
    dag = {"bronze": [], "silver": ["bronze"], "gold": ["silver"]}
    assert downstream_of("bronze", dag) == ["silver"]
    assert downstream_of("silver", dag) == ["gold"]
    assert downstream_of("gold", dag) == []


def test_downstream_of_fan_out():
    dag = {"src": [], "a": ["src"], "b": ["src"], "c": ["a"]}
    assert set(downstream_of("src", dag)) == {"a", "b"}
