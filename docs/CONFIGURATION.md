# Configuration reference

This is the one place that lists every environment variable the project reads. Other guides link here instead of repeating the tables.

- Every variable is optional. Each one has a default, so a fresh clone runs without any configuration.
- No service reads a `.env` file. Set variables in the shell, or put them in a `.env` file next to `docker-compose.yml`, which Docker Compose reads for its own `${...}` substitutions.
- No variable holds a credential. Nothing in the project calls a cloud service or needs an API key. The only secret-like values are the demo PINs in `VITE_WELLBEING_PINS`.
- Relative paths resolve from the working directory of the process. Run each service from its own directory, as the [run guide](RUN-REPO.md) shows.

Setting a variable for one command:

```sh
# Git Bash, macOS, Linux
ONBOARD_TELEMETRY_ENABLED=false uv run fastapi dev
```

```powershell
# Windows PowerShell (the variable stays set for the rest of the session)
$env:ONBOARD_TELEMETRY_ENABLED = "false"; uv run fastapi dev
```

List values (`*_CORS_ORIGINS`) and maps (`WELLBEING_VISION_CAMERAS`) are JSON strings, for example `ONBOARD_CORS_ORIGINS='["http://localhost:1420"]'`.

## onboard-api (`ONBOARD_*`)

Source: [`config.py`](../services/onboard-api/src/onboard_api/config.py). Read once at startup by `create_app`.

| Variable | Default | Used by |
|---|---|---|
| `ONBOARD_DB_PATH` | `data/onboard.db` | All repositories, the assistant's readings provider, the telemetry publisher. The wellbeing module opens the same file read-only. |
| `ONBOARD_MIGRATIONS_DIR` | `<repo>/db/migrations/onboard` | `init_db` at startup |
| `ONBOARD_CORS_ORIGINS` | `["http://localhost:1420", "tauri://localhost", "http://tauri.localhost"]` | CORS middleware. Add an origin when you serve the console from another port. |
| `ONBOARD_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | `OllamaClient` (chat, JSON interpreter, embeddings). Compose: `http://ollama:11434`. |
| `ONBOARD_OLLAMA_CHAT_MODEL` | `qwen2.5:3b` | Local interpreter (`understand_turn`) and answer drafting (`compose_answer`) |
| `ONBOARD_OLLAMA_EMBED_MODEL` | `bge-m3` | Ingest and query embeddings. Must equal `embedding_model` in [`corpus/manifest.json`](../services/onboard-api/corpus/manifest.json), or the ingest aborts. Changing it requires a re-ingest. |
| `ONBOARD_OLLAMA_TIMEOUT_SECONDS` | `20.0` | Each `chat` and `embed` call. The ingest uses at least 120 s. |
| `ONBOARD_OLLAMA_INTERPRET_TIMEOUT_SECONDS` | `15.0` | The `chat_json` call of the local interpreter |
| `ONBOARD_CHROMA_PATH` | `data/chroma` | Guide index (`GuideRetriever`), ingest, `prepare_demo.py` stamp file |
| `ONBOARD_GUIDES_COLLECTION` | `medical_guides` | ChromaDB collection. Must equal `collection` in `corpus/manifest.json`. |
| `ONBOARD_RETRIEVAL_MAX_DISTANCE` | `0.50` | Retrieval drops chunks with a larger cosine distance |
| `ONBOARD_DEMO_EVENTS_PATH` | unset | Optional JSON list of ship events, loaded at startup. Example: [`demo/events.example.json`](../services/onboard-api/demo/events.example.json) (radiation and cabin CO₂ events for `ast-02`). While an event is active, every message for that astronaut gets an `immediate` alarm. |
| `ONBOARD_TELEMETRY_ENABLED` | `true` | Starts the telemetry publisher task |
| `ONBOARD_GROUND_API_URL` | `http://127.0.0.1:8001` | Telemetry publisher and knowledge sync. Compose: `http://ground-api:8001`. |
| `ONBOARD_TELEMETRY_INTERVAL_SECONDS` | `5.0` | Wait between batches and base of the retry backoff |
| `ONBOARD_SHIP_ID` | `ship-01` | `ship_id` in every telemetry batch |
| `ONBOARD_DEMO_CONTROLS_ENABLED` | `false` | Enables `POST /telemetry/pause`, `POST /telemetry/resume` and `DELETE /demo/incidents` ([demo-outage.md](demo-outage.md)). They return 403 while off. |
| `ONBOARD_KNOWLEDGE_DIR` | `data/knowledge` | Approved knowledge bundles (`active/`, `previous/`, `last_sync.json`) |

## Wellbeing module inside onboard-api (`WELLBEING_*`)

Source: [`wellbeing/settings.py`](../services/onboard-api/src/onboard_api/wellbeing/settings.py). Endpoints: [wellbeing-contract.md](wellbeing-contract.md).

| Variable | Default | Used by |
|---|---|---|
| `WELLBEING_DB_PATH` | `data/wellbeing.db` | The module's own database, created and migrated on first use |
| `WELLBEING_ONBOARD_DB_PATH` | `data/onboard.db` | Read-only connection to the onboard database. `ONBOARD_DB_PATH` is also accepted and takes precedence. |
| `WELLBEING_MISSION_TZ` | `UTC` | IANA zone that defines the mission day, for example `America/Tijuana`. An unknown zone fails at startup. |
| `WELLBEING_Z_THRESHOLD`, `WELLBEING_SUSTAIN_DAYS`, `WELLBEING_BASELINE_DAYS`, `WELLBEING_BASELINE_MIN_DAYS`, `WELLBEING_ADAPTATION_DAYS`, `WELLBEING_STALE_AFTER_DAYS`, `WELLBEING_TREND_WINDOW_DAYS`, `WELLBEING_TREND_MIN_DELTA`, `WELLBEING_Z_CAP`, `WELLBEING_MIN_HEART_RATE_READINGS` | `1.5`, `3`, `7`, `5`, `0`, `2`, `3`, `0.5`, `5.0`, `10` | Provisional thresholds and baseline windows of the wellbeing engine. They are not clinical cut-offs. `GET /wellbeing/parameters` returns the active values. |

## ground-api (`GROUND_*`)

Source: [`config.py`](../services/ground-api/src/ground_api/config.py).

| Variable | Default | Used by |
|---|---|---|
| `GROUND_DB_PATH` | `data/ground.db` | Ground database, created at startup. Compose: `/data/ground.db` on the `ground` volume. |
| `GROUND_CORS_ORIGINS` | `["http://localhost:1421", "tauri://localhost", "http://tauri.localhost"]` | CORS middleware |
| `GROUND_DEMO_CONTROLS_ENABLED` | `false` | Enables `DELETE /demo/incidents` |
| `GROUND_BUNDLE_ROOT` | `../..` (the repo root when run from `services/ground-api`) | `GET /medical-eval/approved/bundle` reads the approved component files from here |

## wellbeing-vision (`WELLBEING_VISION_*`)

Source: [`config.py`](../services/wellbeing-vision/src/wellbeing_vision/config.py).

| Variable | Default | Used by |
|---|---|---|
| `WELLBEING_VISION_API_URL` | `http://127.0.0.1:8000` | onboard-api base URL for `POST /wellbeing/vision-sessions` |
| `WELLBEING_VISION_MODELS_DIR` | `models` | Downloaded MediaPipe and OpenCV Zoo models |
| `WELLBEING_VISION_DATA_DIR` | `data` | Neutral-face anchors (`data/neutrals/<astronaut>.jsonl`, numbers only) |
| `WELLBEING_VISION_OUTBOX_PATH` | `outbox/pending.jsonl` | Summaries waiting for the API |
| `WELLBEING_VISION_MIN_FACE_PX` | `160` | Minimum face width for a usable frame (provisional) |
| `WELLBEING_VISION_CAMERAS` | `{"0": "modulo-a", "1": "modulo-b"}` | Camera index to module id |
| `WELLBEING_VISION_ASTRONAUTS` | `{"ast-01": "ast-01", ..., "ast-04": "ast-04"}` | Known astronaut ids |

## Desktop consoles (build-time `VITE_*`)

Vite reads these when the dev server starts or the bundle is built, from the shell or from a `.env` file in the app directory. Restart `npm run tauri dev` after a change.

| Variable | App | Default | Used by |
|---|---|---|---|
| `VITE_ONBOARD_API_URL` | spaceship-app | `http://127.0.0.1:8000` | [`api/client.ts`](../apps/spaceship-app/src/api/client.ts) |
| `VITE_WELLBEING_PINS` | spaceship-app | demo PINs for `ast-01` to `ast-04`; any other astronaut uses `0000` | [`lib/wellbeingPins.ts`](../apps/spaceship-app/src/lib/wellbeingPins.ts). JSON map, for example `VITE_WELLBEING_PINS='{"ast-01":"<pin>"}'`. Demo convenience only: the API has no authentication and the PINs end up in the client bundle. |
| `VITE_GROUND_API_URL` | base-app | `http://127.0.0.1:8001` | [`api/client.ts`](../apps/base-app/src/api/client.ts) |
| `TAURI_DEV_HOST` | both | unset | `vite.config.ts` (Tauri template): host for development on a mobile device |

The Vite ports are fixed in `vite.config.ts` and `src-tauri/tauri.conf.json`: 1420 for spaceship-app and 1421 for base-app, both with `strictPort`. If you change one, change both files and add the new origin to `ONBOARD_CORS_ORIGINS` or `GROUND_CORS_ORIGINS`.

## Docker Compose substitutions

[`docker-compose.yml`](../docker-compose.yml) sets the container paths itself (`ONBOARD_DB_PATH=/data/sqlite/onboard.db`, `WELLBEING_DB_PATH=/data/sqlite/wellbeing.db`, `ONBOARD_CHROMA_PATH=/data/chroma`, `ONBOARD_OLLAMA_BASE_URL=http://ollama:11434`, `GROUND_DB_PATH=/data/ground.db`). These host variables change the stack:

| Variable | Default | Effect |
|---|---|---|
| `ONBOARD_API_HOST` | `127.0.0.1` | Host interface for the onboard-api port. `0.0.0.0` publishes it on the LAN (needed by a real Apple Watch). |
| `ONBOARD_API_PORT` | `8000` | Host port for onboard-api |
| `GROUND_API_PORT` | `8001` | Host port for ground-api |
| `ONBOARD_TELEMETRY_ENABLED` | `true` | Passed to onboard-api and `demo-init` |
| `ONBOARD_GROUND_API_URL` | `http://ground-api:8001` | Passed through. Use `http://host.docker.internal:8001` to reach a native ground-api on the host. |
| `ONBOARD_OLLAMA_CHAT_MODEL`, `ONBOARD_OLLAMA_EMBED_MODEL` | `qwen2.5:3b`, `bge-m3` | Passed through. `demo-init` pulls these models. |
| `DEMO_CONTROLS_ENABLED` | `false` | Sets both `ONBOARD_DEMO_CONTROLS_ENABLED` and `GROUND_DEMO_CONTROLS_ENABLED` |
| `OLLAMA_KEEP_ALIVE` | `-1` | Keeps the models loaded in the `ollama` container |

`ONBOARD_KNOWLEDGE_DIR` is not on a volume in Compose, so an activated knowledge bundle is lost when the container is recreated.

## Command-line tools

These take flags, not environment variables. Each prints its options with `--help`.

| Tool | Working directory | Main flags |
|---|---|---|
| `python firmware/simulator.py` | repo root | `--url` (default `http://127.0.0.1:8000`), `--vitals-every 5`, `--urine-every 600`, `--muscle-every 3600`, `--no-history`, `--seed` |
| `uv run python scripts/seed_demo.py` | `services/onboard-api` | `--url`, `--live` |
| `uv run python -m onboard_api.assistant.ingest` | `services/onboard-api` | `--xml PATH`, `--dry-run` ([RAG guide](RAG-AND-EVALUATION.md)) |
| `uv run python -m onboard_api.assistant.eval` | `services/onboard-api` | `--cases`, `--out`, `--baseline`, `--min-hit-rate`, `--candidate-id` ([RAG guide](RAG-AND-EVALUATION.md)) |
| `uv run python scripts/incident_demo.py` | `services/onboard-api` | `reset`, `run`, `drop`, `restore`, `--step`, `--auto-ack` ([demo-outage.md](demo-outage.md)) |

The Apple Watch app has no environment variables. Its base URL and astronaut are set on the watch ([watch-app README](../apps/watch-app/README.md)).
