# CLAUDE.md — DEX Studio

> Repo-specific context. Workspace-level rules in `../CLAUDE.md`.

## Project Overview

DEX Studio — self-hosted web UI for the DataEngineX platform. Built on Reflex (Python→React).

**Stack:** Python 3.13+ · Reflex 0.7+ · DuckDB · structlog · uv · Ruff · mypy strict · pytest · Port 7860

**Version:** `uv run poe version`

## Build & Run

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
uv run poe check-all
uv run poe dev          # Reflex dev server (port 7860)
```

## Key Modules

| Path | Purpose |
|------|---------|
| `rxconfig.py` | Reflex config (ports, app_name) |
| `src/dex_studio/app.py` | Reflex app + all page registrations |
| `src/dex_studio/state/` | Reflex state classes (base, data, ml, ai, system) |
| `src/dex_studio/components/layout.py` | Sidebar, header, page_shell |
| `src/dex_studio/pages/{data,ml,ai,system}/` | Domain pages |
| `src/dex_studio/_engine.py` | DexEngine singleton (direct package access, no HTTP) |
| `src/dex_studio/engine.py` | DexEngine class — wraps all dataenginex backends |
| `src/dex_studio/config.py` | Studio config (DEX_CONFIG_PATH, theme) |

## CareerDEX

Extracted to standalone package at `../careerdex`. Installed as editable dep via `[tool.uv.sources]`.

<!-- code-review-graph MCP tools -->

## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
1. Use `detect_changes` for code review.
1. Use `get_affected_flows` to understand impact.
1. Use `query_graph` pattern="tests_for" to check coverage.
