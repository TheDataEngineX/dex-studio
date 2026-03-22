ARG SERVICE_PORT=7860

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
ARG SERVICE_PORT

# HuggingFace Spaces runs as non-root user 1000
RUN useradd -m -u 1000 dex

COPY --from=builder /app /app
RUN chown -R 1000:1000 /app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    SERVICE_PORT=${SERVICE_PORT} \
    DEX_STUDIO_HOST=0.0.0.0 \
    DEX_STUDIO_PORT=${SERVICE_PORT} \
    DEX_STUDIO_API_URL=http://localhost:17000 \
    NICEGUI_STORAGE_PATH=/app/.nicegui

EXPOSE ${SERVICE_PORT}
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${SERVICE_PORT}/health')"

USER 1000
CMD ["dex-studio", "--no-native"]
