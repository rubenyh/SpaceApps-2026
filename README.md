# Spaceapps

NASA Space Apps 2026. An astronaut console (Tauri) talks to an onboard FastAPI service with a local medical assistant (Ollama, ChromaDB) and crew readings (SQLite). Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Run the demo (Docker Compose + Tauri)

Docker Compose runs the onboard stack. The Tauri console runs natively on the host. Ground services and physical hardware are not part of the demo.

| Service | What it does |
|---|---|
| `onboard-api` | FastAPI on `http://127.0.0.1:8000`. Applies the SQLite migrations at startup. Starts without Ollama, so alarm and SOS replies keep working when the models are down. |
| `ollama` | Official `ollama/ollama` image. Reachable only inside Compose as `http://ollama:11434`. |
| `demo-init` | One-shot. Waits for Ollama, pulls `qwen2.5:0.5b` and `bge-m3` if missing, and runs the guide ingest when the Chroma index is missing or outdated. Exits 0 when done. Safe to rerun. |
| `simulator` | `firmware/simulator.py`. Starts after the API healthcheck passes, registers `ast-01` and `ast-02`, and posts readings every 5 s. |

Volumes: `sqlite` (`onboard.db` readings and `wellbeing.db`), `chroma` (guide index), `ollama` (models). They survive `docker compose down` and restarts.

### Start

From the repo root (Docker Desktop must be running):

```sh
docker compose up --build        # foreground, Ctrl+C stops
docker compose up --build -d     # or in the background
```

First run downloads about 5 GB: the Ollama image (about 3.2 GB), `bge-m3` (about 1.2 GB), `qwen2.5:0.5b` (about 400 MB), the Python image and dependencies, and the MedlinePlus Health Topics XML used by the ingest. The ingest then embeds the corpus on the CPU, which takes a few minutes. Later starts reuse the volumes and skip all of this.

The API and the simulator are usable before `demo-init` finishes. Until then, educational questions answer without guides and say so in `data_notices`.

### Check setup

```sh
docker compose ps -a                    # demo-init: "Exited (0)" when setup succeeded
docker compose logs demo-init           # pull and ingest progress, lines start with [prepare-demo]
docker compose logs -f simulator        # readings being posted
curl http://127.0.0.1:8000/             # {"status":"ok"}
```

A setup failure leaves `demo-init` with a non-zero exit code and the reason in its log. Rerun only that step with `docker compose up demo-init`.

### Launch the console on Windows

In a second terminal, with Node.js and the Rust toolchain installed:

```sh
cd apps/spaceship-app
npm install
npm run tauri dev
```

The console calls `http://127.0.0.1:8000` by default (`VITE_ONBOARD_API_URL` overrides it). Select `ast-01` to see the live readings.

### Stop

```sh
docker compose down       # stop and remove containers, keep the volumes
docker compose down -v    # also delete the volumes (database, index, models)
```

### Notes

- Port 8000 must be free. Stop any native `uv run fastapi dev` first, or publish another port with `ONBOARD_API_PORT=8010 docker compose up --build` and start the console with `VITE_ONBOARD_API_URL=http://127.0.0.1:8010`.
- Telemetry to ground is off in this stack. To publish to a ground-api running on the host, start with `ONBOARD_TELEMETRY_ENABLED=true` (default target `http://host.docker.internal:8001`, override with `ONBOARD_GROUND_API_URL`).
- Each simulator start uploads its 30-day flash log again, so restarts add more history rows.
- If the corpus or embedding model changes, `demo-init` re-ingests on the next `up`. Restart the API afterwards (`docker compose restart onboard-api`) so it reads the new index.

Native setup without Docker: [`services/onboard-api/README.md`](services/onboard-api/README.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#startup).
