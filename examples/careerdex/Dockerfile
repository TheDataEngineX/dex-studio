ARG PORT=8788

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_PREFERENCE=only-system

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/careerdex
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY LICENSE README.md poe_tasks.toml rxconfig.py ./
COPY src/ src/
RUN uv sync --frozen --no-dev

# Pre-build Reflex frontend; Bun is installed into REFLEX_DIR alongside .web/
ENV REFLEX_DIR=/workspace/careerdex/.reflex \
    PYTHONPATH=src
RUN uv run reflex export --frontend-only

FROM python:3.13-slim
ARG PORT

RUN useradd -m -u 1000 dex

COPY --from=builder /workspace /workspace
RUN chown -R 1000:1000 /workspace
WORKDIR /workspace/careerdex

ENV PATH="/workspace/careerdex/.venv/bin:$PATH" \
    PORT=${PORT} \
    REFLEX_DIR=/workspace/careerdex/.reflex \
    PYTHONPATH=src

EXPOSE ${PORT}

USER 1000
CMD ["careerdex"]
