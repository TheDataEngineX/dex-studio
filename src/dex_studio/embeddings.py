"""Embedding collection management for DEX Studio Intelligence.

Builds vector indexes from gold/silver lakehouse columns using Ollama's
embedding API (nomic-embed-text or any model that supports /api/embed).
Stores vectors + source rows in StudioDb so the lifecycle is aligned with
the rest of the scheduler state — no separate DuckDB files.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import structlog

log = structlog.get_logger().bind(src="embeddings")


def _get_ollama_host(eng: Any) -> str:
    with contextlib.suppress(Exception):
        host = getattr(getattr(eng.config.ai, "llm", None), "host", None)
        if host:
            return str(host).rstrip("/")
    return "http://localhost:11434"


def _get_embed_model(eng: Any, collection_cfg: Any) -> str:
    with contextlib.suppress(Exception):
        model = getattr(collection_cfg, "model", None)
        if model:
            return str(model)
    with contextlib.suppress(Exception):
        vs_cfg = getattr(eng.config.ai, "vectorstore", None)
        if vs_cfg:
            m = getattr(vs_cfg, "embedding_model", None)
            if m:
                return str(m)
    return "nomic-embed-text"


def _embed_texts(texts: list[str], model: str, host: str) -> list[list[float]] | None:
    """Call Ollama /api/embed and return embedding vectors."""
    try:
        import httpx

        resp = httpx.post(
            f"{host}/api/embed",
            json={"model": model, "input": texts},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embeddings") or []
    except Exception as exc:
        log.warning("embed_texts failed", error=str(exc))
        return None


def _load_source_rows(eng: Any, source_table: str, source_col: str) -> tuple[list[Any], str]:
    """Load text rows from a lakehouse parquet file. Returns (rows, error)."""
    import duckdb  # type: ignore[import-untyped]

    layer = _find_layer(eng, source_table)
    if not layer:
        return [], f"Table '{source_table}' not found in any layer"
    parquet_path = eng.project_dir / ".dex" / "lakehouse" / layer / f"{source_table}.parquet"
    if not parquet_path.exists():
        return [], f"Parquet file not found: {parquet_path}"
    safe_col = source_col.replace('"', '""')
    with duckdb.connect(":memory:") as conn:
        rows = conn.execute(
            f'SELECT rowid, "{safe_col}" FROM read_parquet($1) '
            f'WHERE "{safe_col}" IS NOT NULL LIMIT 10000',
            [str(parquet_path)],
        ).fetchall()
    if not rows:
        return [], "No non-null rows found"
    return rows, ""


def _embed_all_batched(
    texts: list[str], model: str, host: str, batch_size: int = 64
) -> tuple[list[list[float]], str]:
    """Embed all texts in batches. Returns (vectors, error)."""
    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        vecs = _embed_texts(texts[i : i + batch_size], model, host)
        if vecs is None:
            return [], "Embedding call failed — is Ollama running with nomic-embed-text?"
        all_vectors.extend(vecs)
    return all_vectors, ""


def _record_collection(
    eng: Any, name: str, source_table: str, source_col: str, model: str,
    count: int, dim: int, duration_s: float,
) -> None:
    with contextlib.suppress(Exception):
        from dex_studio.studio_db import get_studio_db

        db = get_studio_db(eng)
        if db:
            db.upsert_embedding_collection(
                name, source_table, source_col, model, count,
                dim=dim, duration_s=duration_s,
            )


def build_collection(eng: Any, collection_name: str) -> dict[str, Any]:
    """Build an embedding collection from dex.yaml ai.embeddings config."""
    result: dict[str, Any] = {"collection": collection_name, "status": "error"}

    with contextlib.suppress(Exception):
        col_cfg = _resolve_collection_cfg(eng, collection_name)
        if col_cfg is None:
            result["error"] = f"Collection '{collection_name}' not in dex.yaml ai.collections"
            return result

        source_table = str(getattr(col_cfg, "source", "") or "")
        source_col = str(getattr(col_cfg, "column", "") or "")
        if not source_table or not source_col:
            result["error"] = "collection config requires 'source' table and 'column'"
            return result

        model = _get_embed_model(eng, col_cfg)
        host = _get_ollama_host(eng)

        rows, err = _load_source_rows(eng, source_table, source_col)
        if err:
            result["error"] = err
            return result

        texts = [str(r[1]) for r in rows]
        t0 = time.monotonic()
        all_vectors, err = _embed_all_batched(texts, model, host)
        if err:
            result["error"] = err
            return result

        dim = len(all_vectors[0]) if all_vectors else 0
        from dex_studio.studio_db import get_studio_db

        db = get_studio_db(eng)
        if db:
            db.store_vectors(
                collection_name,
                [(r[0], t, v) for r, t, v in zip(rows, texts, all_vectors, strict=True)],
            )
            duration_s = round(time.monotonic() - t0, 1)
            _record_collection(
                eng, collection_name, source_table, source_col, model,
                len(all_vectors), dim, duration_s,
            )

        meta = {
            "collection": collection_name,
            "source_table": source_table,
            "source_column": source_col,
            "model": model,
            "vector_count": len(all_vectors),
            "dim": dim,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_s": round(time.monotonic() - t0, 1),
        }
        result.update(meta)
        result["status"] = "ok"
        log.info(
            "embedding collection built",
            **{k: meta[k] for k in ("collection", "vector_count", "duration_s")},
        )

    return result


def search_collection(
    eng: Any, collection_name: str, query: str, top_k: int = 10
) -> list[dict[str, Any]]:
    """Cosine similarity search over a built embedding collection using numpy."""
    try:
        import numpy as np

        model = _get_embed_model(eng, None)
        host = _get_ollama_host(eng)

        q_vecs = _embed_texts([query], model, host)
        if not q_vecs:
            return [{"error": "Could not embed query", "results": []}]
        q_vec = np.array(q_vecs[0])

        from dex_studio.studio_db import get_studio_db

        db = get_studio_db(eng)
        if db is None:
            return [{"error": "No database available"}]
        vectors_data = db.get_vectors(collection_name)
        if not vectors_data:
            return [{"error": f"Collection '{collection_name}' not built — run Build first"}]

        embeddings = np.array([v["embedding"] for v in vectors_data])
        q_norm = np.linalg.norm(q_vec)
        emb_norms = np.linalg.norm(embeddings, axis=1)
        scores = (embeddings @ q_vec) / (emb_norms * q_norm + 1e-9)
        top_idx = np.argsort(scores)[-top_k:][::-1]

        return [
            {"text": vectors_data[int(i)]["source_text"], "score": round(float(scores[int(i)]), 4)}
            for i in top_idx
        ]

    except Exception as exc:
        log.warning("search_collection failed", collection=collection_name, error=str(exc))
        return [{"error": str(exc)}]


def list_collections(eng: Any) -> list[dict[str, Any]]:
    """List all built embedding collections from StudioDb."""
    from dex_studio.studio_db import get_studio_db

    db = get_studio_db(eng)
    if db is None:
        return []
    return db.get_embedding_collections()


def collection_config(eng: Any) -> list[dict[str, Any]]:
    """Return configured collections from dex.yaml (not necessarily built)."""
    rows: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        ai_cfg = getattr(eng.config, "ai", None)
        collections_cfg = getattr(ai_cfg, "collections", None) or {}
        items = collections_cfg.items() if hasattr(collections_cfg, "items") else []
        for name, cfg in items:
            built_meta = _collection_meta(eng, str(name))
            rows.append(
                {
                    "name": str(name),
                    "source": str(getattr(cfg, "source", "") or ""),
                    "column": str(getattr(cfg, "column", "") or ""),
                    "model": str(getattr(cfg, "model", "") or ""),
                    "built": built_meta is not None,
                    "vector_count": built_meta.get("vector_count", 0) if built_meta else 0,
                    "built_at": built_meta.get("built_at", "—") if built_meta else "—",
                }
            )
    return rows


def _collection_meta(eng: Any, name: str) -> dict[str, Any] | None:
    from dex_studio.studio_db import get_studio_db

    db = get_studio_db(eng)
    if db is None:
        return None
    for col in db.get_embedding_collections():
        if col["name"] == name:
            return {
                "collection": col["name"],
                "source_table": col["source_table"],
                "source_column": col["source_column"],
                "model": col["model"],
                "vector_count": col["vector_count"],
                "built_at": col["built_at"] or "—",
                "dim": col["dim"],
            }
    return None


def _resolve_collection_cfg(eng: Any, collection_name: str) -> Any:
    """Return the collection config object from dex.yaml or None."""
    ai_cfg = getattr(eng.config, "ai", None)
    collections_cfg = getattr(ai_cfg, "collections", None) or {}
    if hasattr(collections_cfg, "get"):
        return collections_cfg.get(collection_name)
    for k, v in collections_cfg.items() if hasattr(collections_cfg, "items") else []:
        if str(k) == collection_name:
            return v
    return None


def _find_layer(eng: Any, table: str) -> str | None:
    for layer in ("gold", "silver", "bronze"):
        with contextlib.suppress(Exception):
            tables = [t["name"] for t in (eng.warehouse_tables(layer) or [])]
            if table in tables:
                return layer
    return None
