# ground-api

The ground FastAPI service. It receives telemetry batches from onboard-api, stores a ground copy of crew, sensors, readings, alerts and incidents in SQLite, and serves that data to the ground console ([base-app](../../apps/base-app/README.md)). It also hosts the medical-eval review and approval API.

- Package `ground_api` in `src/`, app `ground_api.main:app`. Python 3.12, managed with uv. No Ollama, ChromaDB or other external service.
- Data flow and failure behavior: [docs/ARCHITECTURE.md, flow 6](../../docs/ARCHITECTURE.md#6-telemetry-and-ground-console) and [flow 7](../../docs/ARCHITECTURE.md#7-knowledge-release-evaluation-review-activation).
- Environment variables: [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md#ground-api-ground_).

## Run and test

From `services/ground-api`. Use port 8001 so it does not clash with onboard-api.

```sh
uv sync --locked
uv run fastapi dev --port 8001        # http://127.0.0.1:8001
curl http://127.0.0.1:8001/           # {"status":"ok"}
uv run pytest -q
```

At startup the service creates `data/ground.db` (tables are created with `CREATE TABLE IF NOT EXISTS`; there are no migration files). onboard-api starts sending batches on its own when `ONBOARD_TELEMETRY_ENABLED` is true (the default) and `ONBOARD_GROUND_API_URL` points here. Start order does not matter.

In Docker Compose the service runs as `ground-api` on the same port ([root README](../../README.md#quickstart-docker-compose)).

## API

OpenAPI page: <http://127.0.0.1:8001/docs> (schema at `/openapi.json`). Pydantic models: [`schemas.py`](src/ground_api/schemas.py). Telemetry contract: [`contracts/telemetry/README.md`](../../contracts/telemetry/README.md) and [`telemetry.v1.schema.json`](../../contracts/telemetry/telemetry.v1.schema.json), with example batches in [`contracts/telemetry/examples/`](../../contracts/telemetry/examples/).

| Route | Caller | Purpose |
|---|---|---|
| `GET /` | anyone | Health check |
| `POST /telemetry/v1/batches` | onboard-api | Store one batch. 202 with `accepted` and `duplicates`; a repeated `batch_id` writes nothing. 422 for an invalid body. |
| `GET /telemetry/v1/cursor?ship_id=` | onboard-api | Highest reading id stored for the ship (or null), so the ship resumes after it |
| `GET /link` | base-app | Last batch times, counts |
| `GET /crew` | base-app | Crew with sensor status, evaluated with the ground clock |
| `GET /astronauts/{id}/readings` | base-app | Readings, filters `kind`, `since`, `limit` (max 1000) |
| `GET /alerts?limit=` | base-app | Readings outside their health range (max 500) |
| `GET /incidents`, `GET /incidents/{id}` | base-app | Incident updates received from the ship |
| `DELETE /demo/incidents?astronaut_id=` | demo script | 403 unless `GROUND_DEMO_CONTROLS_ENABLED=true` |
| `/medical-eval/...` | operator, base-app | Submit candidates, record decisions and findings, serve the approved bundle ([contract](../../contracts/medical-eval/README.md)) |

Example: `GET /link` while the Compose stack runs.

```json
{
  "ship_id": "ship-01",
  "last_batch_sent_at": "2026-11-15T21:07:14.326253Z",
  "last_batch_received_at": "2026-11-15T21:07:14.333271Z",
  "seconds_since_last_batch": 2,
  "batches_received": 9848,
  "readings_received": 46518
}
```

Example: post a recorded batch by hand (the body follows `telemetry.v1.schema.json`). A second post of the same file returns `accepted: 0`.

```sh
curl -s -X POST http://127.0.0.1:8001/telemetry/v1/batches -H "Content-Type: application/json" \
  --data-binary @../../contracts/telemetry/examples/batch-basic.json
```
