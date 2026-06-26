# DEX Studio — Architecture Reference

Stack: Python 3.13+ · FastAPI · Jinja2 · HTMX · Alpine.js · structlog · port 7860

## Request Lifecycle

```
Browser
  → FastAPI router (src/dex_studio/routers/)
  → require_auth dependency (_deps.py)
  → get_engine() → DexEngine instance (_engine.py)
  → dataenginex library call (direct Python import, no HTTP)
  → Jinja2 template render (templates/)
  → Full HTML response
```

## Partial Updates (HTMX)

Routes that serve HTMX fragments return partial HTML, not full pages:

```
Browser hx-post / hx-get
  → FastAPI route handler
  → dataenginex call
  → templates.TemplateResponse("partials/foo.html", ...)
  → HTML fragment injected into DOM (no full page reload)
```

HTMX handles server round-trips. Alpine.js is used only for local UI state (dropdowns, toggles) that requires no server call.

## Auth

- `POST /login` — validates submitted password via PBKDF2-SHA256 against `~/.dex-studio/auth.hash`
- On success: `session["authenticated"] = True` written into a signed session cookie (`dex_session`)
- Password is set on first boot via `GET /setup`; rate limiter blocks 5 failed attempts for 5 minutes per IP
- All routes call `auth_required(request)` at the top of the handler; unauthenticated requests are redirected to `/login` (303)
- Session cookie is signed by a secret stored at `~/.dex-studio/session.key` (auto-generated on first boot)
- `DEX_HTTPS=1` sets `https_only=True` on the `SessionMiddleware`

## Engine Singleton

`src/dex_studio/_engine.py` holds one `DexEngine` instance for the process lifetime.

- `get_engine()` — returns the singleton, auto-initializing from `DEX_CONFIG_PATH` or the saved default project path
- `init_engine(config_path)` — closes the previous engine (releases DuckDB handles), then constructs a new one; guarded by a `threading.Lock`
- `DexEngine` is imported directly from `dataenginex.engine` — no HTTP, no port 17000

## Routers

`create_app()` in `app.py` registers six routers:

| Router | Prefix |
| -------- | --------- |
| `root` | `/` |
| `data` | `/data` |
| `intelligence` | `/intelligence` |
| `secops` | `/secops` |
| `system` | `/system` |
| `api` | `/api` |

Navigation is driven by `src/dex_studio/nav.py` with two-rail sidebar layout (nav groups: Data, Pipelines, Intelligence, Platform, System).

Shared FastAPI dependencies (engine, auth, template handle) live in `src/dex_studio/routers/_deps.py`.

## Template System

- All page templates: `{% extends "base.html" %}`, override `{% block content %}`
- Templates directory: `src/dex_studio/templates/`
- Jinja2 environment registered with custom filters: `fmt_ts`, `fmt_cron`, `fmt_bytes`, `status_color`
- Template singleton attached to `app.state.templates` at startup

## Static Assets

Served from `src/dex_studio/static/` at `/static/`.

## Projects Registry

`src/dex_studio/config.py` manages two files:

- `~/.dex-studio/projects.yaml` — name → dex.yaml path mapping
- `~/.dex-studio/prefs.yaml` — UI preferences (theme, window size)

Project switching at runtime calls `init_engine(new_path)` which safely tears down and rebuilds the singleton.
