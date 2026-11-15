# Run the repo

How to run the full demo: the onboard stack, ground, both Tauri consoles and, if you want, the wellbeing camera.

```
simulator ──readings──▶ onboard-api :8000 ◀── spaceship-app (Tauri, Vite 1420)
                          │  ├─ SQLite (onboard.db, wellbeing.db)
                          │  ├─ ChromaDB (guides)  ◀── demo-init (ingest)
                          │  └─ ollama (qwen2.5:3b, bge-m3)
                          └──telemetry──▶ ground-api :8001 ◀── base-app (Tauri, Vite 1421)
wellbeing-vision (camera) ──metrics──▶ onboard-api /wellbeing/vision-sessions
```

## Prerequisites

- Docker Desktop, running.
- Node.js and the Rust toolchain (for the Tauri consoles).
- `uv` with Python 3.12 (only for the manual ground-api option and for wellbeing-vision).
- Free ports: 8000, 8001, 1420, 1421. Stop any native `uv run fastapi dev` on 8000 or 8001 first.

## Option A: one command (Windows)

From the repo root, in PowerShell:

```powershell
.\run.ps1
```

The script:

1. Runs `docker compose up --build -d`. This starts `onboard-api`, `ground-api`, `ollama`, `demo-init` and `simulator`.
2. Waits until `http://127.0.0.1:8000/` and `http://127.0.0.1:8001/` answer.
3. Opens one PowerShell window per console (`spaceship-app`, `base-app`). Each window runs `npm install` on first use, then `npm run tauri dev`.

Other forms:

```powershell
.\run.ps1 -NoApps   # only the Docker stack
.\run.ps1 -Down     # stop the Docker stack (keeps the volumes)
```

To stop the consoles, close their windows.

If PowerShell blocks the script ("running scripts is disabled"), run it once with `powershell -ExecutionPolicy Bypass -File .\run.ps1`.

On macOS, from the repo root:

```sh
./run.sh                 # stack + both consoles (one Terminal window each) + watch app in the watchOS simulator
./run.sh --no-apps       # only the Docker stack
./run.sh --watch-device  # also publishes onboard-api on the LAN and opens the watch project in Xcode
./run.sh --urine-device  # also reads ast-01's urine pH/salinity/temperature from the ESP32 on USB (bridge in its own Terminal window)
./run.sh --down          # stop the Docker stack (keeps the volumes)
```

The watch steps run only when `apps/watch-app/` exists and Xcode has a watchOS simulator (`xcodebuild -downloadPlatform watchOS`). The simulator starts as `ast-01` against `http://127.0.0.1:8000`.

On Linux, run `docker compose up --build -d`, then `npm run tauri dev` in `apps/spaceship-app` and in `apps/base-app`.

## Option B: step by step

### 1. Docker stack (terminal 1, repo root)

```sh
docker compose up --build
```

- The first run downloads about 7 GB: the Ollama image, the `bge-m3` and `qwen2.5:3b` models, and the MedlinePlus XML. Embedding the guides then takes a few minutes. Later starts reuse the volumes and skip this.
- The APIs and the simulator work before `demo-init` finishes. Until it finishes, educational questions are answered without guides, and `data_notices` says so.
- `ground-api` is part of the stack. onboard-api sends telemetry to `http://ground-api:8001`. To keep the ship offline, start with `ONBOARD_TELEMETRY_ENABLED=false`.

Check the setup:

```sh
docker compose ps -a              # demo-init: "Exited (0)"
docker compose logs demo-init     # lines start with [prepare-demo]
curl http://127.0.0.1:8000/       # {"status":"ok"}
curl http://127.0.0.1:8001/link   # batches_received grows
```

To run ground-api natively instead, stop the container (`docker compose stop ground-api`), then run `uv sync --locked` and `uv run fastapi dev --port 8001` in `services/ground-api`. onboard-api in Docker reaches it only if you start the stack with `ONBOARD_GROUND_API_URL=http://host.docker.internal:8001`.

### 2. Astronaut console (terminal 2)

```sh
cd apps/spaceship-app
npm install
npm run tauri dev
```

The console calls `http://127.0.0.1:8000` (`VITE_ONBOARD_API_URL` changes this). Select `ast-01` to see the live readings and to use the assistant.

### 3. Ground console (terminal 3)

```sh
cd apps/base-app
npm install
npm run tauri dev
```

The console calls `http://127.0.0.1:8001` (`VITE_GROUND_API_URL` changes this). It shows the crew, the link status, the readings and the alerts that arrive by telemetry. The two consoles use different Vite ports, so they can run at the same time.

### 4. Optional: wellbeing camera (terminal 4)

```sh
cd services/wellbeing-vision
uv sync --locked
uv run wellbeing-vision models                       # once, about 45 MB
uv run wellbeing-vision bitacora --astronaut ast-01  # daily video log
```

Sit facing the camera, about 50 cm away, in good light. The process sends only derived metrics, never frames. Add `--dry-run` to print the JSON without sending it. Details: [`services/wellbeing-vision/README.md`](../services/wellbeing-vision/README.md).

### 5. Optional: Apple Watch (macOS + Xcode)

The watch app shows the astronaut's readings and sends an SOS. `./run.sh` starts it in the watchOS simulator. Compose publishes onboard-api only on `127.0.0.1` by default, so a real watch cannot reach it. For a real watch, use `./run.sh --watch-device` (sets `ONBOARD_API_HOST=0.0.0.0`) or run onboard-api natively with `uv run fastapi dev --host 0.0.0.0`. Install and setup: [`apps/watch-app/README.md`](../apps/watch-app/README.md).

## Check the full flow

1. `docker compose logs -f simulator` shows a reading post every 5 s.
2. spaceship-app shows live vitals for `ast-01`.
3. Ask the assistant a question. An SOS message gets its immediate reply even when `ollama` is stopped.
4. base-app shows the same astronauts and alerts within a few seconds, and the link is up.

Outage demo (urgent incident while the Earth link is down, about 30 s): see [demo-outage.md](demo-outage.md). Its controls (link pause/resume, incident reset) are off by default and answer 403. Start the stack with `$env:DEMO_CONTROLS_ENABLED="true"` in PowerShell (or `DEMO_CONTROLS_ENABLED=true docker compose up -d`) to turn them on. Reset with `python services/onboard-api/scripts/incident_demo.py reset`, then run it with `python services/onboard-api/scripts/incident_demo.py run --step`.

## Stop

```sh
docker compose down       # keeps data, guide index and models
docker compose down -v    # also deletes them
```

Stop native processes with Ctrl+C, or close their windows.

## Notes

- Each simulator start uploads its 30-day flash log again, so restarts add more history rows.
- After `demo-init` re-ingests (the corpus or the embedding model changed), run `docker compose restart onboard-api` so the API reads the new index.
- If ground-api is down, onboard-api retries and sends the backlog later. The start order does not matter.
- Other ports: `ONBOARD_API_PORT=8010` or `GROUND_API_PORT=8011` before `docker compose up`. Then start the matching console with `VITE_ONBOARD_API_URL` or `VITE_GROUND_API_URL` set to the new port.
