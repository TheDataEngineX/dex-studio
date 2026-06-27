# CLAUDE.md — DataEngineX Studio

> Repo-specific context. Workspace-level rules in `../CLAUDE.md`.

## Project Overview

DataEngineX Studio — self-hosted web UI for the DataEngineX platform. Built on FastAPI + Jinja2 (server-side HTML, HTMX).

**Stack:** Python 3.13+ · FastAPI · Jinja2 · HTMX · structlog · uv · Ruff · mypy strict · pytest · Port 7860

**Version:** `uv run poe version`

## Build & Run

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
uv run poe check-all
uv run poe dev          # uvicorn dev server (port 7860)
```

## Key Modules

| Path | Purpose |
|------|---------|
| `src/dex_studio/app.py` | FastAPI app factory — mounts routers, templates, static |
| `src/dex_studio/routers/` | Domain routers: root, data, intelligence, secops, system, api |
| `src/dex_studio/routers/_deps.py` | Shared FastAPI deps (engine, auth, template render) |
| `src/dex_studio/templates/` | Jinja2 HTML templates (base.html + domain pages) |
| `src/dex_studio/static/` | Static assets (CSS, JS) |
| `src/dex_studio/_engine.py` | DexEngine singleton (direct package access, no HTTP) |
| `src/dex_studio/config.py` | Projects registry (~/.dex-studio/projects.yaml) + UI prefs |
| `src/dex_studio/auth.py` | Session-based auth |
| `src/dex_studio/utils.py` | Shared template helpers |
| `src/dex_studio/_json.py` | orjson-backed JSON helpers |
| `src/dex_studio/watermark.py` | Ingestion watermark + hash dedup |
| `src/dex_studio/compaction.py` | Parquet file compaction |
| `src/dex_studio/backfill.py` | Pipeline backfill engine |
