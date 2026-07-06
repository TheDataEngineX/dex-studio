"""GraphQL endpoint smoke test.

/graphql is mounted only when the current project defines
plugins/graphql_schema.py with a build_schema(engine) function (see
dex_studio.app._load_project_graphql_schema). This test fakes that
convention with a throwaway project dir + a tiny table, rather than
depending on the real moviedex example.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient


def _warehouse_table_schema_fn(project_dir: Path) -> Any:
    """Mirror DexEngine.warehouse_table_schema()'s DESCRIBE-based behavior."""

    def _fn(table_name: str, layer: str) -> list[dict[str, Any]]:
        path = project_dir / ".dex" / "lakehouse" / layer / f"{table_name}.parquet"
        if not path.exists():
            return []
        with duckdb.connect(":memory:") as conn:
            conn.execute(f"CREATE VIEW v AS SELECT * FROM read_parquet('{path}')")
            rows = conn.execute("DESCRIBE v").fetchall()
        return [{"column_name": r[0], "column_type": r[1], "nullable": r[3] != "NO"} for r in rows]

    return _fn


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "graphql_schema.py").write_text(
        "from dataenginex.api.graphql import GoldTable\n"
        "from dataenginex.api.graphql import build_schema as _build_generic_schema\n"
        "def build_schema(engine):\n"
        "    return _build_generic_schema(\n"
        "        engine, {'Movie': GoldTable(table='movies', id_column='movie_id')}\n"
        "    )\n"
    )
    gold_dir = tmp_path / ".dex" / "lakehouse" / "gold"
    gold_dir.mkdir(parents=True)
    pq.write_table(
        pa.table({"movie_id": [1, 2], "title": ["Alpha", "Beta"]}),
        gold_dir / "movies.parquet",
    )

    monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
    monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "test-passphrase")
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "test-secret-key-32-chars-xxxxxxx")
    monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=None))
    monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
    monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())

    mock_eng = MagicMock()
    mock_eng.project_dir = tmp_path
    mock_eng.warehouse_table_schema.side_effect = _warehouse_table_schema_fn(tmp_path)

    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        return TestClient(create_app(), raise_server_exceptions=True)


def test_graphql_lists_movies_unauthenticated(client: TestClient) -> None:
    """Reads are public — no login/session needed to hit /graphql."""
    resp = client.post("/graphql", json={"query": "{ movie { movieId title } }"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("errors") is None
    rows = body["data"]["movie"]
    assert len(rows) == 2
    assert {"movieId": 1, "title": "Alpha"} in rows


def test_graphql_filters_by_id(client: TestClient) -> None:
    resp = client.post("/graphql", json={"query": '{ movie(id: "2") { title } }'})
    assert resp.status_code == 200
    assert resp.json()["data"]["movie"] == [{"title": "Beta"}]


def test_graphql_not_mounted_when_project_has_no_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
    monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "test-passphrase")
    monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "test-secret-key-32-chars-xxxxxxx")
    monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=None))
    monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
    monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())

    mock_eng = MagicMock()
    mock_eng.project_dir = tmp_path  # no plugins/graphql_schema.py here

    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        no_gql_client = TestClient(create_app(), raise_server_exceptions=True)

    resp = no_gql_client.post("/graphql", json={"query": "{ __typename }"})
    assert resp.status_code == 404
