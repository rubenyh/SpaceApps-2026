# space-apps-2026

NASA Space Apps 2026 monorepo. An astronaut console (Tauri) talks to an onboard FastAPI service that runs a local assistant and collects crew readings. A ground service receives telemetry.

## Repo map

| Path | What | Status |
|---|---|---|
| `apps/spaceship-app/` | Astronaut console. Tauri 2 + React 19 + Vite 8 + TypeScript 6. Rust crate `spaceship_app_lib`. | Template scaffold |
| `apps/base-app/` | Second Tauri 2 app, same stack. Assumed ground console (name only, no code yet). | Template scaffold |
| `services/onboard-api/` | FastAPI 0.163, Python 3.12, uv. Package `onboard_api` in `src/`. App `onboard_api.main:app`. | Health route only |
| `services/ground-api/` | FastAPI 0.163, Python 3.12, uv. Package `ground_api` in `src/`. App `ground_api.main:app`. | Health route only |
| `.claude/agents/`, `.claude/skills/` | Claude Code subagents and skills. | |

Planned, not in the repo yet: SQLite repository, hardware collectors (pySerial, OpenCV, MediaPipe), LangGraph assistant, Ollama and ChromaDB integrations, telemetry publisher/receiver and contract, console API clients, Python tests (no pytest dependency yet).

## Architecture decisions

- **One assistant, one entry point.** The console calls one onboard endpoint (planned: `POST /assistant/messages`). A parent LangGraph graph routes to workflow subgraphs inside `onboard_api.assistant`. The request/response contract is shared by every workflow. Details: `langgraph-workflows` skill.
- **Medical workflow** (planned): readings from the SQLite repository, guides from ChromaDB, answer from Ollama. Missing or stale data is stated explicitly, never filled in. Answers are informational support only; diagnosis and treatment decisions stay with qualified personnel.
- **Routing:** unclear intent gets one focused clarifying question. Unsupported intent gets a fixed reply that lists what the assistant can do.
- **Psychological support workflow:** possible future work. Do not add its package, routing branch, prompts or Claude Code config until the user confirms scope.
- **Everything runs locally.** No cloud LLM or vector DB calls from the services.
- Integration clients (`assistant/integrations/`) and the monitoring repository are shared across workflows. Never create per-workflow clients.

## Commands (verified 2026-11-14 on Windows)

| Working dir | Command | Notes |
|---|---|---|
| `services/onboard-api` | `uv sync --locked` | Install from `uv.lock`. |
| `services/onboard-api` | `uv run fastapi dev` | Uses `[tool.fastapi] entrypoint`. Default port 8000. `GET /` returns `{"status":"ok"}`. |
| `services/ground-api` | `uv sync --locked` then `uv run fastapi dev --port 8001` | Use a different port than onboard. |
| `services/*` | `uv add <pkg>` / `uv add --dev <pkg>` | Always commit `uv.lock` together with `pyproject.toml`. |
| `apps/spaceship-app` | `npm run build` | `tsc && vite build`. |
| `apps/spaceship-app/src-tauri` | `cargo check` | On Git Bash, cargo is at `~/.cargo/bin/cargo.exe` (not on PATH). |
| `apps/spaceship-app` | `npm run tauri dev` | Not run by Claude (opens a window). Vite port 1420. |

Both Tauri apps use Vite port 1420 with `strictPort`. Do not run them at the same time without changing one port in `vite.config.ts` and `tauri.conf.json`.
On Windows, set `PYTHONUTF8=1` if `fastapi` CLI output fails with `UnicodeEncodeError`.

## Delegation

- Small or single-module changes: do them in the main session.
- Delegate to a subagent when work is deep inside one area:
  - `onboard-backend`: FastAPI routes, config, lifespan, SQLite repository.
  - `hardware-ingestion`: serial, camera, OpenCV, MediaPipe, collectors.
  - `local-assistant`: LangGraph graphs, routing, workflows, prompts, Ollama, ChromaDB.
  - `console-frontend`: Tauri, Rust, React, Vite, console API clients.
  - `telemetry-integration`: onboard publisher, ground receiver, telemetry contract.
- Cross-module work: first agree on the shared interface (Pydantic model, route, JSON schema) in the main session. Then give each subagent a distinct write scope. Then verify the integrated result in the main session.
- Procedures live in `.claude/skills/<name>/SKILL.md`. Keep this file short.
