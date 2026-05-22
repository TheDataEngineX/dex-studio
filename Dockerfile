ARG PORT=7860

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_PREFERENCE=only-system

WORKDIR /workspace/dex-studio
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md poe_tasks.toml ./
COPY src/ src/
COPY examples/ examples/
RUN uv sync --frozen --no-dev


FROM python:3.13-slim
ARG PORT

RUN useradd -m -u 1000 dex

COPY --from=builder /workspace/dex-studio /workspace/dex-studio
RUN chown -R 1000:1000 /workspace

WORKDIR /workspace/dex-studio

ENV PATH="/workspace/dex-studio/.venv/bin:$PATH" \
    PORT=${PORT} \
    PYTHONPATH=src

EXPOSE ${PORT}

USER 1000
CMD ["dex-studio"]
