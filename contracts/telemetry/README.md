# Telemetry contract v1 (ship → ground)

Source of truth for data sent from `onboard-api` to `ground-api`, and for the read API `apps/base-app` uses.
The JSON Schema is [`telemetry.v1.schema.json`](telemetry.v1.schema.json); fixtures live in [`examples/`](examples/).
Only additive changes inside v1. A breaking change means `v2` schema and route.

## Transport

HTTP. The onboard publisher sends `POST {ground}/telemetry/v1/batches` every few seconds.

- Batches are idempotent by `batch_id`; readings are deduplicated by `(ship_id, reading.id)`.
- Ground answers `202 {"accepted": <new readings stored>, "duplicates": <n>}`. Invalid body: `422`.
- On start the publisher asks `GET {ground}/telemetry/v1/cursor?ship_id=<id>` → `{"last_reading_id": <int|null>}` and resumes after it. No onboard migration needed.
- A lost link never blocks onboard work. The publisher retries with backoff and simply sends everything after the cursor when the link returns (bounded batch size, e.g. 500 readings).
- Never sent: camera frames, assistant conversations.

## Batch envelope

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `1` | |
| `ship_id` | string | Onboard setting, default `"ship-01"`. |
| `batch_id` | UUID string | New per batch; reused on retry of the same batch. |
| `sent_at` | ISO 8601 with offset | Onboard clock at send time. |
| `astronauts` | `[{id, display_name}]` | Full crew list every batch (small). |
| `sensors` | `[SensorConfig]` | Full onboard `GET /sensors` list every batch: `kind, unit, stale_after_seconds, normal_min, normal_max, range_role, provisional, range_source`. Ground evaluates status with these. |
| `readings` | `[Reading]` | Same shape as onboard `Reading`: `id` (onboard id), `astronaut_id, kind, value, value_text, unit, recorded_at, received_at, quality, source`. Oldest first. May be empty (heartbeat). |

## Ground read API (for `apps/base-app`)

All JSON, all timestamps ISO 8601 UTC. Ground computes status with **its own clock**, so link delay counts toward staleness. Status rules are the onboard ones (`no_data` → `stale` → `no_range` → `alert`/`normal`).

| Route | Returns |
|---|---|
| `GET /` | `{"status":"ok"}` |
| `GET /link` | `{ship_id, last_batch_sent_at, last_batch_received_at, seconds_since_last_batch, batches_received, readings_received}`. Nulls before the first batch. `ship_id` null until the first batch. |
| `GET /crew` | `[{astronaut_id, display_name, sensors: [SensorStatus]}]`, one per astronaut, sensors in SensorKind order. `SensorStatus` = onboard shape `{kind, status, latest, age_seconds, config}`. `latest` adds `ground_received_at`. |
| `GET /astronauts/{id}/readings?kind=&since=&limit=` | Readings newest first (default limit 100, max 1000). 404 for unknown astronaut. Each reading adds `ground_received_at`. |
| `GET /alerts?limit=` | Newest first (default 50, max 500). One row per stored reading that was outside its **health** range when it arrived: `{reading, normal_min, normal_max, side: "high"\|"low"}`. Sample-validity ranges and `urine_radiation_marker` never produce alerts. |

CORS: ground allows `http://localhost:1421` (base-app Vite dev), `tauri://localhost`, `http://tauri.localhost`.
