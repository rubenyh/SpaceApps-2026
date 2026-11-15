# ground-api image. Build context is services/ground-api (docker-compose.yml).
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependencies first so code changes reuse this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/', timeout=2)"]
CMD ["fastapi", "run", "--host", "0.0.0.0", "--port", "8001"]
