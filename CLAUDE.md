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

## Data Infrastructure UAT Framework

Standing rubric for judging pipeline/warehouse production-readiness. Apply when auditing or reviewing changes to `jobs.py`, `scheduler.py`, `studio_db.py`, `watermark.py`, `compaction.py`, `backfill.py`.

**Data Quality SLAs**
- Reconciliation: 100% row-count/sum match, source vs target.
- Schema integrity: zero unexpected nulls in PK/FK columns.
- Freshness: loaded within window (e.g. daily 6am, or <5min streaming).
- Anomaly frequency: <2 automated DQ alerts/week.

**Operational Reliability KPIs**
- Pipeline success rate: >99% of scheduled runs complete without manual intervention.
- MTTD: alerted within 15 min of failure.
- MTTR: fixed + backfilled within 2 hours for critical dashboards.
- Storage cost efficiency: linear scaling, compression ratios monitored.

**Performance & Usability**
- Query latency P95 <5s. Dashboard load <3s.
- Zero query queuing/timeouts at peak concurrency.
- System availability 99.9%.

**UAT Checklist (pre-signoff)**
- [ ] Source-to-target row-count/checksum validation, all core tables.
- [ ] Historical backfill check — no truncation/corruption.
- [ ] Schema evolution test — pipeline survives source schema change without silent breakage.
- [ ] Stress/concurrency test — 50+ simultaneous analytical queries.
- [ ] Downstream BI validation — dashboard numbers match legacy reports exactly.
- [ ] Permissions/security audit — RBAC restricts PII correctly.
