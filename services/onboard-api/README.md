# onboard-api

The onboard FastAPI service. It stores crew readings in SQLite, evaluates sensor status, runs the local medical assistant (`POST /assistant/messages`: LangGraph, Ollama, ChromaDB), records urgent incidents, serves the wellbeing module and publishes telemetry to ground-api. Everything runs on this machine.

The medical assistant gives informational support only. Diagnosis and treatment decisions stay with qualified personnel.

- Package `onboard_api` in `src/`, app `onboard_api.main:app`. Python 3.12, managed with uv.
- How the parts fit together: [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).
- Environment variables: [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md#onboard-api-onboard_).
- Guide index and evaluations: [docs/RAG-AND-EVALUATION.md](../../docs/RAG-AND-EVALUATION.md).

## Dependencies

| Dependency | Needed for | Without it |
|---|---|---|
| Python 3.12 and [uv](https://docs.astral.sh/uv/) | Everything | |
| SQLite (bundled with Python) | Readings, incidents, wellbeing | |
| Ollama with `qwen2.5:3b` and `bge-m3` | Interpreter on non-alarm turns, drafted explanations, guide search | Alarms and card decisions still work; the reply uses card text and says so in `data_notices` |
| ChromaDB index at `data/chroma` | Guide search | Same fallback as above |
| ground-api | Telemetry | Batches are retried; nothing else is affected |

ChromaDB is a Python dependency (embedded, no server). Ollama and the index are touched only on the first request that needs them, so the service starts without them.

## Run and test

All commands run from `services/onboard-api`. On Windows, set `PYTHONUTF8=1` if output fails with `UnicodeEncodeError`.

```sh
uv sync --locked
uv run fastapi dev                    # http://127.0.0.1:8000, auto-reload
curl http://127.0.0.1:8000/           # {"status":"ok"}
uv run pytest -q                      # unit and API tests, no Ollama or ChromaDB needed
```

`uv run fastapi dev --host 0.0.0.0` listens on the LAN (needed by a real Apple Watch).

At startup the service creates `data/onboard.db` and applies pending migrations from [`db/migrations/onboard/`](../../db/migrations/onboard/) (version in `PRAGMA user_version`). Tables and allowed values: [`db/data-dictionary.md`](../../db/data-dictionary.md).

The tests replace Ollama, ChromaDB and the clock with fakes ([`tests/assistant/fakes.py`](tests/assistant/fakes.py)) and use temporary databases.

For the Docker Compose stack, see the [root README](../../README.md#quickstart-docker-compose).

## Demo data

```sh
# repo root: simulated biomonitor, registers ast-01 and posts live readings
python firmware/simulator.py

# services/onboard-api: one-shot fake readings (source "demo"), --live keeps vitals fresh
uv run python scripts/seed_demo.py [--live]
```

Other scripts in [`scripts/`](scripts/): `prepare_demo.py` (model pull and ingest, the Compose `demo-init` job), `incident_demo.py` ([outage demo](../../docs/demo-outage.md)), `simulate_wellbeing.py`, `demo_reset.py` and `import_apple_health.py` ([wellbeing runbook](../../docs/wellbeing-demo-runbook.md)).

## API

The interactive OpenAPI page is at <http://127.0.0.1:8000/docs> and the schema at <http://127.0.0.1:8000/openapi.json> while the service runs. The Pydantic models in [`src/onboard_api/schemas/`](src/onboard_api/schemas/) are the source of truth; the console mirrors them by hand in [`apps/spaceship-app/src/api/types.ts`](../../apps/spaceship-app/src/api/types.ts).

| Route | Purpose |
|---|---|
| `GET /` | Health check |
| `GET /astronauts`, `POST /astronauts` | List and register crew (409 if the id exists) |
| `PATCH /astronauts/{id}` | Rename: `{"display_name": "..."}`, same validation as `POST` (404 if the id does not exist) |
| `GET /astronauts/{id}/status` | Latest reading and status (`normal`, `alert`, `stale`, `no_data`, `no_range`) per sensor |
| `POST /readings`, `GET /readings` | Store a reading; list one astronaut's readings, newest first (`astronaut_id` required; `kind`, `since`, `until`, `limit` up to 1000) |
| `GET /sensors`, `PUT /sensors/{kind}` | Sensor units, ranges and staleness limits |
| `POST /assistant/messages` | The assistant. One request and response contract for every workflow. |
| `GET /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/acknowledgments`, `POST /incidents/{id}/close` | Urgent incidents created by `immediate` assistant replies |
| `GET /telemetry/link` | State of the link to ground |
| `POST /telemetry/pause`, `POST /telemetry/resume`, `DELETE /demo/incidents` | Outage demo controls; 403 unless `ONBOARD_DEMO_CONTROLS_ENABLED=true` |
| `GET /knowledge/active`, `POST /knowledge/sync`, `POST /knowledge/rollback` | Approved knowledge bundle ([flow 7](../../docs/ARCHITECTURE.md#7-knowledge-release-evaluation-review-activation)) |
| `/wellbeing/...`, `/astronauts/{id}/wellbeing/...` | Wellbeing module: [docs/wellbeing-contract.md](../../docs/wellbeing-contract.md) |

The assistant contract and what the console shows: [docs/assistant-frontend-integration.md](../../docs/assistant-frontend-integration.md).

### Examples

Store a reading. Exactly one of `value` or `value_text` is set, `unit` must match the sensor config, and `recorded_at` needs a UTC offset. Returns 201, or 404 for an unknown astronaut and 422 for a wrong unit.

```sh
curl -s -X POST http://127.0.0.1:8000/readings -H "Content-Type: application/json" --data-binary @- <<'EOF'
{"astronaut_id": "ast-01", "kind": "heart_rate", "value": 74, "unit": "bpm",
 "recorded_at": "2026-11-15T21:07:11Z", "quality": "good", "source": "manual"}
EOF
```

Read the sensor status. Response, shortened:

```json
{
  "astronaut_id": "ast-01",
  "generated_at": "2026-11-15T21:07:16.026146Z",
  "sensors": [
    {
      "kind": "heart_rate",
      "status": "normal",
      "latest": {"astronaut_id": "ast-01", "kind": "heart_rate", "value": 74.0, "value_text": null, "unit": "bpm",
                 "recorded_at": "2026-11-15T21:07:11.068868Z", "quality": "good", "source": "simulated:pulse-ox",
                 "id": 46515, "received_at": "2026-11-15T21:07:11.075283Z"},
      "age_seconds": 4,
      "config": {"kind": "heart_rate", "unit": "bpm", "stale_after_seconds": 300, "normal_min": 60.0, "normal_max": 100.0,
                 "range_role": "health", "provisional": true, "range_source": "AHA / Mayo Clinic"}
    }
  ]
}
```

Ask the assistant. A headache without detail gets one focused question and an open case in `clarification`:

```sh
curl -s -X POST http://127.0.0.1:8000/assistant/messages -H "Content-Type: application/json" --data-binary @- <<'EOF'
{"astronaut_id": "ast-01", "message": "I have a headache"}
EOF
```

Response, shortened (the full response also has `reply`, `steps`, `report`, `sources`, `matched_rules`, `findings` and more):

```json
{
  "workflow": "medical",
  "needs_clarification": true,
  "urgency": "undetermined",
  "protocol_id": "neurologic_red_flags",
  "action": "Headache with unknown onset and severity: check for neurological warning signs.",
  "notify": ["mission control (if the link is up)"],
  "data_notices": [],
  "disclaimer": "Informational support only. Diagnosis and treatment decisions belong to qualified personnel.",
  "clarifying_question": "Did the headache start suddenly and is it very severe, or does it come with speech disturbance, facial drooping, weakness on one side or loss of vision?",
  "clarification": {"question_id": "neurologic_red_flags.headache_red_flags", "question": "...", "astronaut_id": "ast-01", "observations": ["..."]},
  "incident": null
}
```

To answer, send the `clarification` object back unchanged with only the answer in `message`. A message such as `"I have chest pressure and a cold sweat"` returns `urgency: "immediate"` at once from the local protocol cards, and records an incident (`incident.id`). Messages may be English or Spanish; replies are English.

PowerShell equivalent of the assistant call:

```powershell
$body = @{ astronaut_id = "ast-01"; message = "I have a headache" } | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8000/assistant/messages -ContentType "application/json; charset=utf-8" -Body $body
```

In Git Bash on Windows, `curl -d '...'` with accented characters failed with "There was an error parsing the body"; the heredoc with `--data-binary @-` avoids it.
