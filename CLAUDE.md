# CLAUDE.md — DEX Studio

Always Be pragmatic, straight forward and challenge my ideas and system design focus on creating a consistent, scalable, and accessible user experience while improving development efficiency. Always refer to up to date resources as of today. Question my assumptions, point out the blank/blind spots and highlight opportunity costs. No sugarcoating. No pandering. No bias. No both siding. No retro active reasoning. If there is something wrong or will not work let me know even if I don't ask it specifically. If it is an issue/bug/problem find the root problem and suggest a solution refering to latest day resources — don't skip, bypass, supress or don't fallback to a defense mode.

> Repo-specific context. Workspace-level rules, coding standards, and git conventions are in `../CLAUDE.md`.

## Project Overview

**DEX Studio** — Local Python-first desktop UI. Single control plane for the full DataEngineX platform.

**Stack:** Python 3.13+ · NiceGUI · pywebview · httpx · uv · Ruff · mypy strict · pytest · Port 7860

**Version:** `uv run poe version` | **Standalone** — connects to a running DEX engine via HTTP (no Python dependency on dataenginex)

## Build & Run Commands

```bash
uv run poe setup             # install all deps (including dev)

uv run poe lint              # ruff lint
uv run poe typecheck         # mypy strict (src/dex_studio/ only)
uv run poe test              # pytest
uv run poe check-all         # lint + typecheck + test

uv run poe dev               # browser mode (development, port 7860)
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
