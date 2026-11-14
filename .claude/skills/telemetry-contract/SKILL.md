---
name: telemetry-contract
description: Define and evolve the ship-to-ground telemetry contract and implement the onboard publisher and ground-api receiver against it. Use when a change touches data sent from onboard-api to ground-api.
---

# Telemetry contract (planned)

Status: nothing exists yet; both services have only a health route. Transport is not decided. Default proposal: HTTP POST from onboard to ground, since both are FastAPI. Confirm with the user before choosing something else.

## Where (proposed)
- Contract: `contracts/telemetry/` at repo root, with `telemetry.v1.schema.json` (JSON Schema) and `examples/*.json` fixtures. This is the source of truth.
- Publisher: `services/onboard-api/src/onboard_api/telemetry/publisher.py`.
- Receiver: `services/ground-api/src/ground_api/telemetry.py`, route `POST /telemetry/v1/batches`.
- The services are separate uv projects, so each defines its own Pydantic models that match the schema. Fixture tests keep them in sync.

## Do
- Envelope fields: `schema_version`, `ship_id`, `batch_id` (UUID, for idempotent retry), `sent_at`, `readings[]` (each with `astronaut_id`, `kind`, `value`, `unit`, `recorded_at`).
- Only additive changes inside a version. A breaking change means a new `vN` schema and route.
- The publisher reads through the monitoring repository, batches, and retries with backoff. A lost link never blocks collectors or the assistant. Bound the queue and count dropped batches.
- The receiver validates, deduplicates by `batch_id`, and returns 202.
- Ground URL and send interval come from onboard settings.
- Never send raw camera frames or assistant conversations unless the user approves it.

## Verify
- In each service: a test that every file in `contracts/telemetry/examples/` parses into its Pydantic model.
- Receiver tests with `TestClient`: valid batch gives 202, a duplicate batch is stored once, invalid gives 422.
- Optional end to end: ground-api on 8001, onboard-api on 8000, check one batch arrives.

Docs: https://json-schema.org/understanding-json-schema , https://fastapi.tiangolo.com/tutorial/body/
