---
name: fastapi-uv
description: Run, extend and add dependencies to the FastAPI services (services/onboard-api, services/ground-api) managed with uv. Use when adding routes, settings, lifespan resources, Python dependencies, or running either service.
---

# FastAPI + uv

## Where
- `services/onboard-api/` - package `onboard_api` (src layout), app `onboard_api.main:app`.
- `services/ground-api/` - package `ground_api`, app `ground_api.main:app`.
- Each has `pyproject.toml`, `uv.lock`, `.python-version` (3.12). Build backend `uv_build`.
- `[tool.fastapi] entrypoint` lets `fastapi dev` find the app without arguments.
- `[project.scripts]` entries (`onboard-api`, `ground-api`) call `main()` in `__init__.py`; today it only prints a greeting. It is not the server.

Versions from manifests/lock: `fastapi[standard]>=0.163.0` (locked 0.163.0), uv 0.12.x.

## Do
- Run commands from the service dir.
- Add deps: `uv add <pkg>`; dev-only: `uv add --dev <pkg>`. Commit `uv.lock` with `pyproject.toml` in the same change.
- Imports use the package name: `from onboard_api.storage import ...`. Never `from src...`.
- Put long-lived resources (DB, Ollama client, Chroma client) in a `lifespan` context manager on `FastAPI(lifespan=...)`, store on `app.state`, read via `Depends`.
- Settings: one module (planned `onboard_api/config.py`) reading env vars; `.env` is gitignored.
- Group routes with `APIRouter` per area and `app.include_router(...)`.
- Console calls from Tauri webview need `CORSMiddleware` allowing `http://localhost:1420` (dev) and the Tauri production origin (`http://tauri.localhost` on Windows, `tauri://localhost` on macOS/Linux).
- ground-api `main.py` title currently says "Space Apps Onboard API" (copy-paste); fix when touching it.

## Verify
```bash
uv sync --locked
uv run python -c "import onboard_api.main"
uv run fastapi dev            # ground-api: --port 8001
curl http://127.0.0.1:8000/   # {"status":"ok"}
```
Tests (planned): `uv add --dev pytest httpx`, then `uv run pytest`. Use `fastapi.testclient.TestClient`.
Windows: `PYTHONUTF8=1` if the CLI raises `UnicodeEncodeError`.

Docs: https://fastapi.tiangolo.com/advanced/events/ , https://fastapi.tiangolo.com/fastapi-cli/ , https://docs.astral.sh/uv/concepts/projects/
