# space-apps-2026

NASA Space Apps 2026 monorepo. An astronaut console (Tauri) talks to an onboard FastAPI service that runs a local assistant and collects crew readings. A ground service receives telemetry and serves a ground console. Human docs: `README.md` (quickstart), `docs/` (architecture, configuration, RAG and evaluation, troubleshooting), `CONTRIBUTING.md`.

## Repo map

| Path | What | Status |
|---|---|---|
| `apps/spaceship-app/` | Astronaut console. Tauri 2 + React 19 + Vite 8 + TypeScript 6. Rust crate `spaceship_app_lib`. Vite port 1420. Shares one visual identity with base-app (tokens: `src/styles/tokens.css`). | Status, vitals, muscle, urine, assistant, records, wellbeing |
| `apps/base-app/` | Ground console, same stack and visual identity. Talks only to ground-api. Vite port 1421. | Crew, astronaut, alerts, incidents, medical eval, link |
| `apps/watch-app/` | Apple Watch app, watchOS 10+ SwiftUI, watch-only (no iPhone app). Polls onboard-api status and open incidents; 2 s hold sends SOS to `POST /assistant/messages`. Replaces ARCHeR (no live API). Setup: `apps/watch-app/README.md`. | Readings, SOS, incident alert |
| `services/onboard-api/` | FastAPI 0.163, Python 3.12, uv. Package `onboard_api` in `src/`. App `onboard_api.main:app`. | Readings API, SQLite repository, `POST /assistant/messages` (LangGraph medical workflow, Ollama, ChromaDB), incidents, wellbeing, telemetry publisher, knowledge gate, eval runner, pytest |
| `services/ground-api/` | FastAPI 0.163, Python 3.12, uv. Package `ground_api` in `src/`. App `ground_api.main:app`. | Telemetry receiver, ground read API, medical-eval review, pytest |
| `services/wellbeing-vision/` | Camera collector for the wellbeing module. Python 3.12, uv, OpenCV + MediaPipe. Own process, CLI `wellbeing-vision`. Sends derived metrics only (never frames) to onboard-api `POST /wellbeing/vision-sessions` and `/wellbeing/co-presence`. | Daily video log, face identity, two-camera ambient mode |
| `firmware/` | `simulator.py`: software stand-in for the biomonitor device (pulse-ox, urine analyser, muscle scanner). Posts to onboard-api `/readings` with source `simulated:*`; buffers while the API is down. Stdlib only. | Simulated until real hardware exists |
| `db/` | SQLite migrations (`db/migrations/onboard/` applied at onboard-api startup, `db/migrations/wellbeing/` on first wellbeing use) and `db/data-dictionary.md`. ground-api creates its own tables in code. | |
| `contracts/`, `eval/medical/` | Telemetry v1 and medical-eval contracts; synthetic medical eval cases (all `draft`). | |
| `.claude/agents/`, `.claude/skills/` | Claude Code subagents and skills. | |

Planned, not in the repo yet: hardware collectors for real sensors (pySerial, OpenCV, MediaPipe pose).

## Architecture decisions

- **One assistant, one entry point.** The console calls one onboard endpoint, `POST /assistant/messages`. A parent LangGraph graph routes to workflow subgraphs inside `onboard_api.assistant`. The request/response contract is shared by every workflow. Details: `langgraph-workflows` skill.
- **Medical workflow:** rules and protocol cards decide urgency; readings from the SQLite repository, guides from ChromaDB, answer from Ollama. Missing or stale data is stated explicitly, never filled in. Answers are informational support only; diagnosis and treatment decisions stay with qualified personnel.
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
| repo root | `python3 firmware/simulator.py` | Live device feed for the console (needs onboard-api running). `--urine-every 120` for faster samples. Self-check: `cd firmware && python3 test_simulator.py`. |
| repo root | `python firmware/muscle_live.py` | Phone-slider demo feed for the Muscle screen's live graph (port 8765, prints LAN URL). Memory only, never posts to onboard-api. Self-check: `--check`. |
| `apps/spaceship-app` | `npm run build` | `tsc && vite build`. |
| `apps/spaceship-app/src-tauri` | `cargo check` | On Git Bash, cargo is at `~/.cargo/bin/cargo.exe` (not on PATH). |
| `apps/spaceship-app` | `npm run tauri dev` | Not run by Claude (opens a window). Vite port 1420. |
| `apps/watch-app` | `xcodebuild -project WatchApp.xcodeproj -target WatchApp -sdk watchsimulator build` | macOS + Xcode only. Self-check: `swiftc WatchApp/Api.swift Checks/main.swift -o /tmp/watch-checks && /tmp/watch-checks`. A real watch needs onboard-api started with `uv run fastapi dev --host 0.0.0.0`. |

Vite ports (`strictPort`): spaceship-app 1420, base-app 1421, so both can run at once. Exception: spaceship-app's HMR also takes 1421 when `TAURI_DEV_HOST` is set (mobile dev).
On Windows, set `PYTHONUTF8=1` if `fastapi` CLI output fails with `UnicodeEncodeError`.

## Delegation

Small or single-module changes: do them in the main session. Delegate when work is deep inside one area:

| Subagent | Delegate when |
|---|---|
| `onboard-backend` | FastAPI routes, config, lifespan, SQLite repository |
| `hardware-ingestion` | Serial, camera, OpenCV, MediaPipe, collectors |
| `local-assistant` | LangGraph graphs, routing, workflows, prompts, Ollama, ChromaDB |
| `console-frontend` | Tauri, Rust, React, Vite, console API clients |
| `telemetry-integration` | Onboard publisher, ground receiver, telemetry contract |
| `documentation-maintainer` | A change affects setup commands, architecture, API or telemetry contracts, or the demo. Owns README, diagrams, `docs/`. Writes docs only. |

- Cross-module work: first agree on the shared interface (Pydantic model, route, JSON schema) in the main session. Then give each subagent a distinct write scope. Then verify the integrated result in the main session.
- Procedures live in `.claude/skills/<name>/SKILL.md`. Keep this file short.

## Git workflow (parallel sessions)

Several Claude Code accounts and sessions work in parallel. Git and `origin` are the coordination channel.

1. **Fetch before starting.** Run `git status` and `git fetch origin`. Check remote branches and open PRs for overlapping work. Start each independent task on a new branch from `origin/main` named `agent/<owner>/<task>`. Concurrent sessions sharing one checkout use separate worktrees (`git worktree add --no-track -b agent/<owner>/<task> ../<dir> origin/main`). Use `--no-track` (or `git switch --no-track -c ...`) so the branch never tracks `main`.
2. **Keep ownership clear.** One writer per branch. Parallel agents get distinct file scopes. Agree on shared interfaces before parallel changes. Preserve other sessions' commits and local edits. If remote changes overlap yours, inspect the diff and coordinate with the owner before resolving. Never force-push shared branches.
3. **Use Conventional Commits:** `<type>(<scope>): <description>`, scope optional. Examples: `chore(claude): add documentation maintainer`, `docs(architecture): describe onboard workflows`, `fix(telemetry): validate capture timestamps`. Use the same format for PR titles. Spec: https://www.conventionalcommits.org/en/v1.0.0/
4. **Push checkpoints and hand off in the PR.** Push the task branch early (`git push -u origin <branch>`). Use a draft PR while work is in progress. Keep the PR description current: scope, checks run, remaining work. Before requesting merge, fetch again, review `git diff origin/main...HEAD`, and run the relevant checks.
5. **Only merging into `main` needs the user's explicit approval.** Without asking you may create branches and worktrees, commit, push task branches, and open or update PRs. When a PR is ready, send the user its link and check results, then wait for approval before merging. Merge with a merge commit (`gh pr merge <n> --merge`), never squash or rebase, so each commit stays in `main`. All changes to `main` go through an approved PR. Keep auto-merge off and respect branch protection.
