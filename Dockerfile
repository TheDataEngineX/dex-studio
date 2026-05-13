ARG SERVICE_PORT=7860

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /workspace/dex-studio
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/

FROM python:3.13-slim
ARG SERVICE_PORT

RUN useradd -m -u 1000 dex

COPY --from=builder /workspace /workspace
RUN chown -R 1000:1000 /workspace
WORKDIR /workspace/dex-studio

ENV PATH="/workspace/dex-studio/.venv/bin:$PATH" \
    SERVICE_PORT=${SERVICE_PORT} \
    DEX_STUDIO_HOST=0.0.0.0 \
    DEX_STUDIO_PORT=${SERVICE_PORT} \
    DEX_STUDIO_API_URL=http://localhost:17000

EXPOSE ${SERVICE_PORT}

USER 1000
CMD ["dex-studio"]
