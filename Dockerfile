ARG PORT=7860

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_PREFERENCE=only-system

WORKDIR /workspace/dex-studio
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev

COPY . .
RUN uv sync --no-dev


FROM python:3.13-slim
ARG PORT

RUN useradd -m -u 1000 dex

COPY --from=builder /workspace /workspace
RUN chown -R 1000:1000 /workspace

WORKDIR /workspace/dex-studio

ENV PATH="/workspace/dex-studio/.venv/bin:$PATH" \
    PORT=${PORT} \
    PYTHONPATH=src

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-7860}/health')" || exit 1

USER 1000
# Ensure .dex directory exists for database files
RUN mkdir -p /home/dex/.dex
CMD ["dex-studio"]
