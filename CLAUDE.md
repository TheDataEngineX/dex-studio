# CLAUDE.md — DEX Studio

> Repo-specific context. Workspace-level rules, coding standards, and git conventions are in `../CLAUDE.md`.

## Project Overview

**DEX Studio** — Local Python-first desktop UI. Single control plane for the full DataEngineX platform.

**Stack:** Python 3.11+ · NiceGUI · pywebview · httpx · uv · Ruff · mypy strict · pytest · Port 8080

**Version:** 0.1.0 | **Standalone** — connects to a running DEX engine via HTTP (no Python dependency on dataenginex)

## Build & Run Commands

```bash
uv run poe setup             # install all deps (including dev)

uv run poe lint              # ruff lint
uv run poe typecheck         # mypy strict (src/dex_studio/ only)
uv run poe test              # pytest
uv run poe check-all         # lint + typecheck + test

uv run poe dev               # browser mode (development, port 8080)
uv run poe dev-native        # native window mode
```

## Key Files

| File | Purpose |
| --- | --- |
| `src/dex_studio/` | Core UI app |
| `src/dex_studio/cli.py` | Entry point (`dex-studio` command) |
| `src/dex_studio/app.py` | NiceGUI app setup |
| `src/dex_studio/pages/` | UI pages (health, quality, lineage, ML, settings) |
| `src/dex_studio/client.py` | httpx async client to DEX API |
| `poe_tasks.toml` | All task definitions |
