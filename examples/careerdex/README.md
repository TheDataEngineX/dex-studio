# CareerDEX — Example

AI-powered career intelligence — job search, application tracking, resume building, interview prep, networking, progress analytics.

This is the **folded-back v0 implementation** of CareerDEX. Originally a standalone repo (`TheDataEngineX/careerdex`), it was archived and merged back into `dex-studio/examples/` per [ADR-0007](https://github.com/TheDataEngineX/docs/blob/main/adr/0007-local-first-scope-reset.md): CareerDEX is a **domain example** of an app you can build on top of [`dataenginex`](https://github.com/TheDataEngineX/dex), not a separate product.

______________________________________________________________________

## Status

**Stack:** Reflex (Python → React). This is the **v0** code preserved from the original repo.

**Integration with `dex-studio`:** not yet. Currently runs as its own Reflex app inside this folder. Porting it to `dex-studio`'s FastAPI + Jinja2 + HTMX shell is **Phase 5** in the [2026 roadmap](https://github.com/TheDataEngineX/docs/blob/main/docs/roadmap/DESIGN-2026.md).

**Why folded back instead of deleted:** the data models, services, and aggregator code (~14 k LOC) are reusable. The Reflex pages are reference for the future port.

______________________________________________________________________

## What's inside

```text
examples/careerdex/
├── src/careerdex/
│   ├── models/           # Pydantic models — job, application, resume, networking, story,
│   │                     # evaluation, portal, vector_db, email, rag_eval, progress
│   ├── services/         # Business logic — job aggregators (Greenhouse, Indeed, Lever,
│   │                     # LinkedIn, Workday), ATS scanner, resume builder, cover-letter
│   │                     # generator, interview prep, negotiation, networking, scheduler,
│   │                     # vector search, RAG eval, scoring, …
│   ├── pages/career/     # Reflex pages (30+) — analytics, applications, dashboard,
│   │                     # discover, interview, jobs, network, resume, tracker, …
│   ├── state/            # Reflex state classes — career, jobs
│   ├── components/       # Reflex UI components
│   ├── data/questions/   # YAML data — behavioral & technical interview questions
│   ├── templates/        # Jinja2 templates — resume_classic.html.j2
│   ├── app.py / careerdex.py / cli.py
├── tests/                # unit + integration tests (~20 files)
├── pyproject.toml        # standalone package config (for running the Reflex app in isolation)
├── rxconfig.py           # Reflex config
├── Dockerfile            # builds the Reflex app
└── poe_tasks.toml        # dev tasks (lint, test, dev server)
```

______________________________________________________________________

## Running the Reflex app in isolation

For now, treat this directory as a standalone Reflex project:

```bash
cd examples/careerdex
uv sync
uv run poe dev          # starts the Reflex dev server
```

Or via Docker:

```bash
cd examples/careerdex
docker build -t careerdex .
docker run -p 3000:3000 careerdex
```

The Reflex app is **separate from** the `dex-studio` web server. It does not currently share state, sessions, or auth with `dex-studio`. That integration arrives in the Phase 5 port.

______________________________________________________________________

## Migration plan (Phase 5)

| Step | What changes |
| --- | --- |
| 1. Models stay | `src/careerdex/models/` — Pydantic models port 1:1 |
| 2. Services stay | `src/careerdex/services/` — business logic is stack-agnostic; minor edits for `dataenginex` integration |
| 3. State → DexStore | Reflex state classes become `dataenginex` config + DuckDB-backed persistence |
| 4. Pages → routers | Reflex `pc.page` decorators replaced with FastAPI routes returning Jinja2 templates |
| 5. UI → HTMX/Alpine | Reflex components rewritten as Jinja2 partials + HTMX interactions |
| 6. Drop Reflex deps | `pyproject.toml` and `rxconfig.py` removed; the example becomes a `dex.yaml` + custom routers registered into `dex-studio` |

The [`dex-studio` design brief](../../DESIGN-BRIEF-2026.md) and the [`Dex Studio - Claude Design/`](../../Dex%20Studio%20-%20Claude%20Design/) mocks reflect the target stack for the ported version.

______________________________________________________________________

## Why CareerDEX matters as an example

It demonstrates an end-to-end application built on `dataenginex`:

- **Data ingestion** from heterogeneous sources (job-board aggregators, user-uploaded resumes, scraped portals)
- **Quality / matching pipelines** (ATS scanning, resume-to-JD matching, scoring)
- **ML / AI** (resume evaluation, interview prep with RAG, semantic job search via embeddings)
- **Domain UI** built on top of a generic workbench

That's the kind of app the broader local-first audience (students preparing job applications, indie consultants, small recruiters) can build and self-host on their own data.

______________________________________________________________________

## License

Inherits MIT from `dex-studio` (see top-level [`LICENSE`](../../LICENSE)).
