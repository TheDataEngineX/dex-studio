# Changelog

All notable changes to `dex-studio` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.1] - 2026-06-30

### Added

- **PostgreSQL dual-backend** (`PgStudioDb`) — when `DATABASE_URL` is set, scheduler state, pipeline locks, run history, watermarks, and schema contracts are stored in Postgres instead of SQLite. Uses `pg_advisory_lock` for cross-pod pipeline mutual exclusion and scheduler leader election.
- **Multi-pod scheduler leader election** — only one pod runs the scheduler tick when multiple instances share a Postgres database.

### Fixed

- **`jobs.py` — missing `set_last_run()` on manual runs** — background runs triggered via the UI (`run_pipeline_bg`, `run_all_pipelines_bg`) now call `sdb.set_last_run()` on success, so the cron scheduler correctly records last-run timestamps and doesn't re-fire completed pipelines on the next tick.

## [0.5.0] - 2026-06-23

### Added

- **Two-rail navigation** — sidebar nav groups (Data, Pipelines, Intelligence, Platform, System) with icon badges; active-rail highlighting
- **Intelligence domain** — unified `intelligence` router (replaces separate `ml` + `ai` routers): Playground (SSE streaming chat), Models, Experiments, Dashboard, Agents, Traces, Drift, Embeddings, Features, Predictions, Tools, Finetune
- **System domain expansion** — Scheduler, Runs, Compaction, Alerting, Costs dashboards
- **Data domain expansion** — Quality checks, Lineage graph, Transform editor, Streaming monitors, Backfill management, Watermark tracking
- **Scripts** — `scripts/demo/browser_segments.py` (Playwright screenshot capture), `scripts/demo/record.py` (Playwright video recording)
- **nav.py** — single source of truth for sidebar nav structure
- **studio_db.py** — Studio-level SQLite backing store
- **dag.py** — pipeline DAG utilities
- **tools/** — Tool registry
- **Quality module** (`quality.py`) — data quality check framework
- **Embeddings module** (`embeddings.py`) — embedding management UI
- **Execution UI** (`execution.py`) — pipeline execution tracking
- **Backfill tracker** (`backfill.py`) — backfill pipeline management
- **Compaction manager** (`compaction.py`) — storage compaction UI

### Changed

- **Router consolidation** — `ml` and `ai` routers merged into single `intelligence` router with `/intelligence` prefix
- **Template reorganization** — `templates/intelligence/` replaces `templates/ml/` and `templates/ai/`
- **Navigation** — `nav.py` drives all sidebar rendering; router names normalized to match nav groups
- **Version** — bumped to 0.5.0

### Removed

- `routers/ml.py` and `routers/ai.py` — replaced by `routers/intelligence.py`
- `templates/ml/` and `templates/ai/` — replaced by `templates/intelligence/`

## [0.4.0] - 2026-06-12

First public release.

### Added

- **Full UI redesign** — oklch-based design system with dark/light theme, Inter + JetBrains Mono font stack, Radix-inspired color tokens, and a coherent component library (cards, pills, buttons, progress bars, dialogs)
- **FastAPI Depends auth layer** — `ReadDep`, `WriteDep`, `JsonReadDep` dependency injectors replace the legacy `guard()` pattern; all routers migrated
- **CSRF protection** — token seeded at login, enforced on every mutating request via `WriteDep`; HTMX wired via `X-CSRF-Token` header
- **Security headers middleware** — `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and `Content-Security-Policy` on all responses
- **Top page loader** — 3 px fixed accent bar fires on every HTMX request and native form submit
- **Button loading states** — global form submit handler applies `.loading` + `aria-busy="true"` spinner to submit buttons; `data-no-loading` opt-out
- **Indeterminate progress bar** — `@keyframes indeterminate` + `.progress > i.indeterminate` for pipeline run strips (animation was referenced but never defined)
- **Pagination** — numbered page buttons with ellipsis; threshold lowered to 10 rows (was 15); per-table `data-page-size` and `data-page-threshold` attributes
- **Delta connector page** — UI surface for `DeltaConnector` catalog registration
- **Flow canvas** — visual pipeline DAG viewer (`data/flow_canvas.html`)
- **Jobs module** (`jobs.py`) — background task lifecycle helpers for arq integration
- **Flow module** (`flow.py`) — pipeline DAG utilities for the UI

### Changed

- **Scheduler** — module-level globals replaced with `app.state` for async-safe multi-worker operation
- **Macros** (`components/macros.html`) — all Radix `rt-*` classes replaced with native dex-studio classes (`card`, `pill`, `btn`, semantic table HTML)
- **Default bind address** — `0.0.0.0` → `127.0.0.1` in CLI and uvicorn startup
- **SSE log stream** — all three log fields (`ts`, `level`, `msg`) HTML-escaped to prevent XSS

### Removed

- `audit.py`, `client.py`, `dex_studio.py` — dead code deleted
- Entire `rt-*` Radix UI compat block and dead layout shims removed from `studio.css` (~104 lines)

### Security

- **File permissions** — API key file and session secret file created with `0o600`
- **Path traversal** — `catalog_register` resolves paths and confirms they are under `project_dir` before accepting
- **SQL sandbox** — `FROM '/path'` DuckDB literal syntax added to blocklist preventing file-read via the SQL console
- **Pre-auth guard** — onboarding state-change endpoints now require authentication
- **CSRF seeding** — token is set on successful login so all subsequent POSTs are protected immediately

[0.4.0]: https://github.com/TheDataEngineX/dex-studio/releases/tag/v0.4.0
