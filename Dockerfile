FROM python:3.12-slim

# HuggingFace Spaces runs as non-root user 1000
RUN useradd -m -u 1000 dex

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml README.md ./
COPY src/ src/

# Install without optional GTK/Qt native backends (browser mode only)
RUN uv pip install --system .

USER 1000

# HF Spaces requires port 7860
# DEX_STUDIO_* env vars override connection settings
ENV DEX_STUDIO_HOST=0.0.0.0 \
    DEX_STUDIO_PORT=7860 \
    DEX_STUDIO_API_URL=http://localhost:8000

EXPOSE 7860

CMD ["dex-studio", "--no-native"]
