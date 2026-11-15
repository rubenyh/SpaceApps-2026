# onboard-api image. Build context is the repo root (docker-compose.yml) so the
# root db/ migrations land where init_db expects them: <repo>/db/migrations/onboard.
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    PATH="/app/services/onboard-api/.venv/bin:$PATH"
WORKDIR /app/services/onboard-api

# Dependencies first so code changes reuse this layer.
COPY services/onboard-api/pyproject.toml services/onboard-api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY db /app/db
COPY services/onboard-api ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)"]
CMD ["fastapi", "run", "--host", "0.0.0.0", "--port", "8000"]
