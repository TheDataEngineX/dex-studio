ARG SERVICE_PORT=7860

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Build from parent DataEngineX/ directory:
#   docker build -f dex-studio/Dockerfile -t dex-studio .
# (needed until dataenginex drops rich dep and a new PyPI release ships)
WORKDIR /workspace
COPY dex/ dex/
COPY dex-studio/ dex-studio/

WORKDIR /workspace/dex-studio
RUN uv sync --frozen --no-dev

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
