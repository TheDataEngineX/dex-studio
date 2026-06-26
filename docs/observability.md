# Observability: Metrics, Logging & Tracing

**Application-level observability for DEX Studio.** For library-level metrics (Prometheus instrumentation, OpenTelemetry spans), see [dataenginex/docs/observability.md](https://github.com/TheDataEngineX/dataenginex/blob/main/docs/observability.md).

## Logging

DEX Studio uses `structlog` for structured logging. All log output is written to stdout with a console-friendly format.

### Viewing Logs

- **In the UI**: Navigate to **System → Logs** for a live SSE-backed log tail.
- **On the console**: `uv run poe dev` streams logs to stderr.
- **In Docker**: `docker compose logs -f dex-studio`.

### Structured Fields

Every log entry includes:
- `ts` — ISO-8601 timestamp
- `level` — `debug` / `info` / `warning` / `error`
- `event` — short human-readable message
- `src` — source module (`app`, `_engine`, `auth`, etc.)
- `request_id` — correlation ID (set via `X-Request-ID` header)
- `path` — URL path (on request-scoped logs)

### Captured Logs

The in-app log viewer captures all `structlog` entries and mirrors stdlib logging (uvicorn, FastAPI, library loggers) via `install_stdlib_handler()`.

## Metrics

DEX Studio does not expose its own Prometheus `/metrics` endpoint. Library-level metrics (pipeline run counters, model prediction latency, etc.) are instrumented in `dataenginex` and can be scraped from the application that mounts it.

To export metrics, add to your FastAPI app:

```python
from dataenginex.observability.metrics import setup_metrics
from prometheus_client import make_asgi_app

app.mount("/metrics", make_asgi_app())
```

## Tracing

DEX Studio sets `X-Request-ID` and `Server-Timing` headers on every response. OpenTelemetry distributed tracing is configured at the library level (`dataenginex`); enable it via:

```bash
export OTLP_ENDPOINT="http://localhost:4317"
```

## Health Checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Returns engine health status — `{"status": "healthy"}` when the `DexEngine` singleton is connected and responsive. |

## Slow Request Detection

A middleware logs a warning for any request taking > 1s:

```text
[warning] slow request  path=/data/quality  method=GET  ms=2450
```
