# Run the repo

Every way to run the system: the Docker Compose stack, a native setup, both Tauri consoles, the wellbeing camera and the Apple Watch. The short version is the [README quickstart](../README.md#quickstart). Variables: [CONFIGURATION.md](CONFIGURATION.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

```
simulator ──readings──▶ onboard-api :8000 ◀── spaceship-app (Tauri, Vite 1420)
                          │  ├─ SQLite (onboard.db, wellbeing.db)
                          │  ├─ ChromaDB (guides)  ◀── demo-init (ingest)
                          │  └─ ollama (qwen2.5:3b, bge-m3)
                          └──telemetry──▶ ground-api :8001 ◀── base-app (Tauri, Vite 1422)
wellbeing-vision (camera) ──metrics──▶ onboard-api /wellbeing/vision-sessions
```

## Prerequisites

- Docker Desktop, running.
- Node.js and the Rust toolchain (for the Tauri consoles).
- `uv` with Python 3.12 (only for the native options and for wellbeing-vision), and Ollama for the native option with LLM answers.
- Free ports: 8000, 8001, 1420, 1422. Stop any native `uv run fastapi dev` on 8000 or 8001 first.

## Compose services

| Service | What it does |
|---|---|
| `onboard-api` | FastAPI on `http://127.0.0.1:8000`. Applies the SQLite migrations at startup. Does not depend on Ollama, so alarm and SOS replies work while the models are down. |
| `ground-api` | FastAPI on `http://127.0.0.1:8001`. Receives telemetry from `onboard-api` and serves base-app. |
| `ollama` | Official `ollama/ollama` image. Reachable only inside Compose as `http://ollama:11434`; port 11434 is not published. Keeps models loaded (`OLLAMA_KEEP_ALIVE=-1`). |
| `demo-init` | One-shot job ([`prepare_demo.py`](../services/onboard-api/scripts/prepare_demo.py)). Waits for Ollama, pulls `qwen2.5:3b` and `bge-m3` if missing, loads them, and builds the guide index when it is missing or outdated. Exits 0 when done. Safe to rerun. |
| `simulator` | [`firmware/simulator.py`](../firmware/simulator.py). Starts after the API healthcheck passes, registers `ast-01` and `ast-02`, uploads a 30-day history and posts readings every 5 s. |

Volumes: `sqlite` (`onboard.db`, `wellbeing.db`), `chroma` (guide index), `ollama` (models), `ground` (`ground.db`). They survive `docker compose down` and restarts; `docker compose down -v` deletes them.

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
./run.sh --urine-device  # also reads ast-01's urine pH/salinity/temperature from the ESP32 on USB (bridge in its own Terminal window; Windows: `.\run.ps1 -UrineDevice`)
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

### 6. Optional: live muscle demo with a phone slider (terminal 5, repo root)

```sh
python firmware/muscle_live.py        # add --port N to change port 8765
```

Startup prints two URLs: a LAN URL such as `http://192.168.1.20:8765/` for the phone, and `http://127.0.0.1:8765/` for testing on the computer. To set it up:

1. Connect the phone to the same Wi-Fi as the computer. Guest networks and networks with client isolation block phone-to-computer traffic.
2. The first time, allow Python through the Windows Defender Firewall prompt on **Private** networks. Without this, the phone cannot load the page.
3. Open the LAN URL on the phone.

The slider sets a target value from 0 kg to 5 kg. Once per second, the server makes one sample from the target plus random variation of up to ±0.10 kg. Each sample stays within 0 kg to 5 kg. On the **Muscle** screen, the console plots the last 60 samples in **Live muscle reading**, above the muscle density trend. The panel is labeled **Simulated**. While the server is down, the panel shows a waiting or disconnected state. It reconnects on its own when the server returns.

This feed is separate from the rest of the system. The console reads only `GET /samples` from this server, which keeps samples in memory. Nothing is sent to onboard-api, so the feed never reaches the stored muscle density history, the assistant or telemetry. Set `VITE_MUSCLE_LIVE_URL` if the console must read the feed from another host or port. Self-check: `python firmware/muscle_live.py --check`.

## Option C: native, without Docker

Run onboard-api, ground-api and the simulator as local processes: [README, local development](../README.md#quickstart-local-development). Then start the consoles as in steps 2 and 3 above. Optional extras for the native setup:

- Demo ship events (a radiation and a cabin CO₂ alarm for `ast-02`): start onboard-api with `ONBOARD_DEMO_EVENTS_PATH=demo/events.example.json`.
- One-shot fake readings instead of the live simulator: `uv run python scripts/seed_demo.py [--live]` in `services/onboard-api`.
- Faster simulator samples: `python3 firmware/simulator.py --urine-every 120`. Self-check without the API: `cd firmware && python3 test_simulator.py`.

## Check the full flow

1. `docker compose logs -f simulator` shows a reading post every 5 s.
2. spaceship-app shows live vitals for `ast-01`.
3. Ask the assistant a question. An SOS message gets its immediate reply even when `ollama` is stopped.
4. base-app shows the same astronauts and alerts within a few seconds, and the link is up.

Outage demo (urgent incident while the Earth link is down, about 30 s) and the case report demo (ship to base across an outage and an onboard restart): see [demo-outage.md](demo-outage.md). Its controls (link pause/resume, incident reset) are off by default and answer 403. Start the stack with `$env:DEMO_CONTROLS_ENABLED="true"` in PowerShell (or `DEMO_CONTROLS_ENABLED=true docker compose up -d`) to turn them on. Reset with `python services/onboard-api/scripts/incident_demo.py reset`, then run it with `python services/onboard-api/scripts/incident_demo.py run --step`.

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
