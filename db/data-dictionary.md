# Data dictionary: onboard database

SQLite database of `services/onboard-api` (`ONBOARD_DB_PATH`, default `data/onboard.db`, relative to the working directory, git-ignored). `ground-api` keeps its own SQLite copy (`GROUND_DB_PATH`, default `data/ground.db`; tables `batches`, `astronauts`, `sensors`, `readings`, `alerts`, `incidents`, `incident_updates`, `case_reports`), created in code by [`storage.py`](../services/ground-api/src/ground_api/storage.py) and not described here.

Schema and reference data: [`migrations/onboard/0001_baseline.sql`](migrations/onboard/0001_baseline.sql) , [`migrations/onboard/0002_incidents.sql`](migrations/onboard/0002_incidents.sql), [`migrations/onboard/0003_incident_origin.sql`](migrations/onboard/0003_incident_origin.sql) and [`migrations/onboard/0004_case_reports.sql`](migrations/onboard/0004_case_reports.sql). If this document and the SQL differ, the SQL wins.

Readings are informational support only. Diagnosis and treatment decisions stay with qualified personnel.

## Conventions

- **Timestamps** are `TEXT` in UTC, fixed-width ISO 8601: `YYYY-MM-DDTHH:MM:SS.ffffffZ` (e.g. `2026-11-14T09:30:00.000000Z`). Fixed width (always 6 fractional digits, always `Z`) makes string comparison equal chronological comparison, so `ORDER BY recorded_at DESC`, the `since`/`until` filters and the index work on plain text. SQLite does not check the format; the app writes every timestamp through `to_db_timestamp` and reads with `from_db_timestamp` ([`database.py`](../services/onboard-api/src/onboard_api/repositories/database.py)). The API rejects timestamps without a UTC offset and converts the rest to UTC.
- **Booleans** are `INTEGER` 0/1.
- "API" limits below come from the Pydantic models in [`schemas/`](../services/onboard-api/src/onboard_api/schemas/). They are not enforced by SQLite.

## `astronauts`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | PK | | API: `^[a-z0-9][a-z0-9-]{1,31}$` (`schemas/astronauts.py`). |
| `display_name` | TEXT | NOT NULL | | API: 1 to 80 characters. |
| `created_at` | TEXT | NOT NULL | | Timestamp, set by the server. |

Referenced by `readings.astronaut_id`.

## `sensor_config`

One row per sensor kind: unit, validity window and reference range. Edited with `PUT /sensors/{kind}` (unknown kind: 404; rows cannot be added or deleted through the API).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `kind` | TEXT | PK | | App-level `SensorKind` (`schemas/sensors.py`): `heart_rate`, `spo2`, `muscle_density`, `urine_ph`, `urine_salinity`, `urine_color`, `urine_temperature`, `urine_radiation_marker`. No SQL CHECK. `GET /sensors` and the status endpoint ignore rows whose kind is not in `SensorKind`. |
| `unit` | TEXT | NULL | | Unit that readings of this kind must use. NULL: unit not defined yet, any unit is accepted. |
| `stale_after_seconds` | INTEGER | NULL | | Seconds after `recorded_at` when the latest reading stops counting as current. API: > 0. NULL: never stale (see [Freshness](#freshness)). |
| `normal_min` | REAL | NULL | | Lower bound of the reference range, in `unit`. API: not greater than `normal_max`. |
| `normal_max` | REAL | NULL | | Upper bound. Both NULL: no range, status `no_range`. |
| `range_role` | TEXT | NOT NULL | `'health'` | CHECK `IN ('health','sample_validity')` (app: `RangeRole`). `sample_validity`: the range says whether the sample is usable, not whether the astronaut is healthy (urine temperature). |
| `provisional` | INTEGER | NOT NULL | `1` | 1: values are placeholders pending review. No SQL CHECK; the API writes 0 or 1. |
| `range_source` | TEXT | NULL | | Free-text reference for the range. |
| `updated_at` | TEXT | NOT NULL | | Timestamp of the last change. Seeded rows use the migration time with `.000000` microseconds. |

Referenced by `readings.kind`.

### Reference rows (seeded by 0001, all `provisional = 1`)

| `kind` | `unit` | `stale_after_seconds` | `normal_min` | `normal_max` | `range_role` | `range_source` |
|---|---|---|---|---|---|---|
| `heart_rate` | `bpm` | 300 | 60 | 100 | health | AHA / Mayo Clinic |
| `spo2` | `%` | 300 | 95 | 100 | health | Mayo Clinic |
| `muscle_density` | NULL | 604800 | NULL | NULL | health | NULL |
| `urine_ph` | `pH` | 86400 | 4.6 | 8.0 | health | MedlinePlus |
| `urine_salinity` | NULL | 86400 | NULL | NULL | health | NULL |
| `urine_color` | `rgb_hex` | 86400 | NULL | NULL | health | NULL |
| `urine_temperature` | `°C` | 86400 | 32 | 38 | sample_validity | 49 CFR 40.65 |
| `urine_radiation_marker` | NULL | 86400 | NULL | NULL | health | NULL |

These are demo values, not clinically validated thresholds.

`urine_radiation_marker` is urinary 8-OHdG (8-hydroxy-2'-deoxyguanosine), an indirect marker of oxidative DNA damage, not a dose. The 0001 seed leaves it unconfigured. At boot, `firmware/simulator.py` sets it with `PUT /sensors/urine_radiation_marker` (only while `unit` is NULL): `unit` `ng/mg creatinine`, `stale_after_seconds` 86400, `normal_min` 3.0, `normal_max` 5.5, `range_role` health, `provisional` 1, `range_source` `Graille et al. 2020 (8-OHdG meta-analysis)` (healthy-adult IQR, chemical methods). Consoles show its value and range, but it never raises the console alert banner or the ground alert log.

`urine_salinity` is urine electrical conductivity. The 0001 seed leaves it unconfigured. At boot, `firmware/simulator.py` and `firmware/serial_bridge.py` set it with `PUT /sensors/urine_salinity` (only while `unit` is NULL): `unit` `mS/cm`, `normal_min` 5.6, `normal_max` 30.3, `range_role` health, `provisional` 0 (mean ± 1.96 SD of 1,064 healthy adults on a Sysmex UF-1000i). The bridge converts the board's TDS with `mg/L ÷ 500`, an assumed probe factor.

## `readings`

One crew reading. Rows are only inserted (`POST /readings`); the API has no update or delete.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | | |
| `astronaut_id` | TEXT | NOT NULL | | FK `astronauts(id)`. API returns 404 for an unknown astronaut. |
| `kind` | TEXT | NOT NULL | | FK `sensor_config(kind)`. See [Kind and unit checks](#kind-and-unit-checks). |
| `value` | REAL | NULL | | Numeric value in `unit`. |
| `value_text` | TEXT | NULL | | Non-numeric value. API: 1 to 64 characters. `urine_color` is sent as `#RRGGBB` (documented convention; the API does not validate the pattern). |
| `unit` | TEXT | NOT NULL | | API: 1 to 32 characters, must equal `sensor_config.unit` unless that is NULL. |
| `recorded_at` | TEXT | NOT NULL | | Capture time (from the client), timestamp. |
| `received_at` | TEXT | NOT NULL | | Time the server stored the row, timestamp. |
| `quality` | TEXT | NOT NULL | | CHECK `IN ('good','suspect','bad')` (app: `Quality` in `schemas/readings.py`). |
| `source` | TEXT | NOT NULL | | Origin, e.g. `manual`, `serial:pulse`, `serial:urine-analyser` (ESP32, `firmware/serial_bridge.py`; `urine_salinity` converted from the board's `mg/L` TDS to `mS/cm`, the unit of simulated rows). API: 1 to 64 characters. |

Table CHECK `(value IS NULL) <> (value_text IS NULL)`: exactly one of `value` and `value_text` is set. The API checks the same rule before inserting (422).

### Kind and unit checks

- `kind REFERENCES sensor_config(kind)` is enforced: `connect()` runs `PRAGMA foreign_keys = ON` on every connection (SQLite leaves it off by default). The same applies to `astronaut_id`.
- The API first validates `kind` against `SensorKind` (422 for other values).
- `record_reading` in [`services/readings.py`](../services/onboard-api/src/onboard_api/services/readings.py) then loads the `sensor_config` row: `unit` must match exactly when the configured unit is not NULL (otherwise 422); a NULL configured unit accepts any unit. A missing row raises a server error, because every `SensorKind` is seeded.

### Index

`idx_readings_lookup ON readings (astronaut_id, kind, recorded_at DESC)`: serves "latest reading of one kind" (`ReadingRepository.latest`) and the filtered, newest-first list (`ReadingRepository.search`).

## `incidents` (version 2, origin columns version 3)

One urgent medical incident. Created by `POST /assistant/messages` when the response has `urgency = 'immediate'` ([`repositories/incidents.py`](../services/onboard-api/src/onboard_api/repositories/incidents.py)). Read with `GET /incidents` and `GET /incidents/{id}`.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | PK | | UUID v4, generated onboard (never an integer: ground deduplicates by id across DB resets). |
| `trigger_key` | TEXT | NOT NULL | | `"<astronaut_id or ''>\|<sorted rule ids>\|<sorted event ids>"`. Rule ids are `matched_rules[].rule_id` plus `sos` for the SOS path (console or watch SOS text, so both share one open incident); event ids come from findings with source `event:<id>`. |
| `status` | TEXT | NOT NULL | `'open'` | CHECK `IN ('open','closed')`. |
| `astronaut_id` | TEXT | NULL | | Assessed person from the request. No FK: the request may name an unknown or no astronaut. |
| `reported_by` | TEXT | NULL | | Crewmate who sent the request, from the request. No FK. |
| `began_at` | TEXT | NOT NULL | | Timestamp, onboard server clock when the incident was created. |
| `closed_at` | TEXT | NULL | | Timestamp, set by `POST /incidents/{id}/close`. |
| `urgency` | TEXT | NOT NULL | | Response urgency (`immediate`). |
| `action` | TEXT | NULL | | Immediate action of the response. |
| `protocol_id` | TEXT | NULL | | Primary protocol card. |
| `steps_json` | TEXT | NOT NULL | | JSON `list[ActionStep]` (`schemas/assistant.py`). |
| `matched_rules_json` | TEXT | NOT NULL | | JSON `list[MatchedRule]`: `rule_id`, `protocol_id`, `protocol_version`, `urgency`. |
| `findings_json` | TEXT | NOT NULL | | JSON `list[Finding]`, including `evidence_flags`. |
| `data_notices_json` | TEXT | NOT NULL | | JSON `list[str]`. |
| `mission_procedures_json` | TEXT | NOT NULL | | JSON `list[MissionProcedure]`. |
| `missing_guidance_json` | TEXT | NOT NULL | | JSON `list[str]`. |
| `reported_via` | TEXT | NULL | | Version 3. CHECK `IN ('console','watch')`: `source` of the request that created the incident. NULL for rows created before version 3. A reuse keeps the original value. |
| `reading_ids_json` | TEXT | NOT NULL | `'[]'` | Version 3. JSON `list[int]` of `readings.id`: the latest reading per kind for the astronaut when the incident was created (same readings the medical workflow shows). `[]` for rows created before version 3, or when no astronaut or no readings. |

Unique partial index `incidents_open_trigger (trigger_key) WHERE status = 'open'`: one open incident per trigger. The same trigger while it is open reuses the incident; after it is closed, a new incident is created.

## `incident_events` (version 2)

Status history of each incident (`created` by the assistant, `acknowledged` by `POST /incidents/{id}/acknowledgments`, `closed` by `POST /incidents/{id}/close`) and the queue of incident updates for ground telemetry. The `incidents` row and its `created` event are inserted in one transaction.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | PK | | UUID v4; also the telemetry update id. |
| `incident_id` | TEXT | NOT NULL | | FK `incidents(id)`. |
| `type` | TEXT | NOT NULL | | CHECK `IN ('created','acknowledged','closed')`. |
| `occurred_at` | TEXT | NOT NULL | | Timestamp of the original onboard event, server clock. |
| `acknowledged_by` | TEXT | NULL | | FK `astronauts(id)`. Only for `acknowledged`. |
| `delivered_at` | TEXT | NULL | | NULL: queued for ground. Set only after ground-api answers 2xx for the batch that carried it. |

Indexes: unique `incident_events_created (incident_id) WHERE type = 'created'`; unique `incident_events_ack (incident_id, acknowledged_by) WHERE type = 'acknowledged'`; `incident_events_queue (occurred_at) WHERE delivered_at IS NULL`.

`ground_delivery` in the API is computed, never stored: `disabled` when `ONBOARD_TELEMETRY_ENABLED` is false, else `queued` if any event has `delivered_at` NULL, else `delivered`.

## `case_reports` (version 4)

Crew-reviewed case reports ([contract](../contracts/case-report/README.md)) and the ship to ground report queue. A draft is stored for each assistant reply with `report.id`; `POST /case-reports/{id}/send` queues it; the telemetry publisher sends queued rows to ground. Repository: [`case_reports.py`](../services/onboard-api/src/onboard_api/repositories/case_reports.py).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | PK | | Report UUID v4 from the assistant reply (`report.id`); the ground `report_id`. |
| `astronaut_id` | TEXT | NULL | | Assessed person from the request. No FK. |
| `reported_by` | TEXT | NULL | | Crewmate who sent the request. No FK. |
| `urgency` | TEXT | NOT NULL | | Reply urgency; `undetermined` when the reply has none. |
| `protocol_id` | TEXT | NULL | | Primary protocol card. |
| `action` | TEXT | NULL | | Reply action. |
| `assessed_at` | TEXT | NOT NULL | | Timestamp, onboard clock when the readings were loaded (draft time if the reply has none). |
| `created_at` | TEXT | NOT NULL | | Timestamp, draft stored. |
| `text` | TEXT | NOT NULL | | Report body as previewed. |
| `readings_json` | TEXT | NOT NULL | | JSON `list[SnapshotReading]` (`report.readings`). |
| `knowledge_version_json` | TEXT | NULL | | JSON `{candidate_id, digest}` of the active bundle, or NULL. |
| `incident_id` | TEXT | NULL | | Onboard incident id for an `immediate` reply. No FK. |
| `status` | TEXT | NOT NULL | `'draft'` | CHECK `IN ('draft','queued','received','failed')`. Send moves `draft` or `failed` to `queued`; ground's acknowledgement moves `queued` to `received`; a permanent ground rejection to `failed`. |
| `sent_by` | TEXT | NULL | | Crew member who pressed send. |
| `queued_at` | TEXT | NULL | | Timestamp of the send; the contract's `sent_at`. |
| `received_at` | TEXT | NULL | | Ground's receipt time from its acknowledgement. |
| `error` | TEXT | NULL | | Reason for `failed`; cleared on resend. |

Index `case_reports_queue (queued_at) WHERE status = 'queued'`. `DELETE /demo/incidents?astronaut_id=` deletes the astronaut's rows.

## Freshness

`GET /astronauts/{id}/status` ([`services/status.py`](../services/onboard-api/src/onboard_api/services/status.py)) and the assistant `SqliteReadingsProvider` ([`assistant/workflows/medical/context.py`](../services/onboard-api/src/onboard_api/assistant/workflows/medical/context.py)) share one rule, `freshness()` in `services/status.py`, against the onboard clock when the readings are read:

| Case | Result |
|---|---|
| `recorded_at` more than 5 s ahead of the clock (`FUTURE_SKEW_SECONDS`) | `future`, age 0. Shown with a clock warning, not evaluated, never current evidence. Status endpoint: status `future`. |
| `age > stale_after_seconds` (age = `now - recorded_at`, clamped to 0) | `stale`. |
| Otherwise, or `stale_after_seconds` NULL | `current`. |

Difference: with no `sensor_config` row, the status endpoint does not list the kind; the assistant uses 300 s (`DEFAULT_STALE_AFTER_SECONDS`).

## Version and migrations

- Schema version is `PRAGMA user_version`. Migration files are `db/migrations/onboard/NNNN_<slug>.sql`; `NNNN` is the `user_version` the database has after that file. `0001_baseline.sql` is version 1, `0002_incidents.sql` is version 2, `0003_incident_origin.sql` is version 3, `0004_case_reports.sql` is version 4. A database gets only the pending files and keeps its rows.
- `init_db` in [`database.py`](../services/onboard-api/src/onboard_api/repositories/database.py) runs at service start-up. Each pending migration runs in one transaction together with its `PRAGMA user_version = N`; on error it rolls back, leaving schema and version unchanged. Rerunning is a no-op. A database newer than the latest file is rejected.
- Legacy databases (version 0 with the tables already present) are compared with the 0001 schema; on a match only `user_version` is set to 1 (no data change), otherwise start-up fails naming the difference.
- After migrating, `PRAGMA foreign_key_check` must report no violations, or start-up fails.
- Migrations directory: resolved from the package location by default; override with `ONBOARD_MIGRATIONS_DIR`.
- New schema change: add the next numbered file. Never edit an applied migration.

---

# Data dictionary: wellbeing database

SQLite database of the wellbeing module in `services/onboard-api` (`WELLBEING_DB_PATH`, default `data/wellbeing.db`, relative to the working directory, git-ignored). It is a separate file from `onboard.db`: the module reads `onboard.db` read-only (`mode=ro`, through `AstronautRepository` and `ReadingRepository`) and never writes to it.

Schema: [`migrations/wellbeing/0001_baseline.sql`](migrations/wellbeing/0001_baseline.sql) and [`migrations/wellbeing/0002_ground_packages.sql`](migrations/wellbeing/0002_ground_packages.sql). If this document and the SQL differ, the SQL wins. API contract: [`docs/wellbeing-contract.md`](../docs/wellbeing-contract.md).

The module supports people and never diagnoses. No images, video or face templates are stored: only derived metrics.

## Conventions

- **Timestamps**: same format and helpers as `onboard.db` (see [Conventions](#conventions)).
- **Days** (`day`) are `TEXT` `YYYY-MM-DD`, the mission day in `WELLBEING_MISSION_TZ` (IANA name, default `UTC`). Fixed width, so text order is chronological. Only `checkins.day` is stored; every other day is derived from the UTC timestamps at query time, so changing the zone regroups them without migrating data.
- **`astronaut_id`** refers to `onboard.db` `astronauts(id)`, which is in another file, so there is no foreign key. The API checks existence (404). Vision rows may carry `unknown-<track>` for an unidentified person: stored, never used in any baseline.
- **`body`** columns hold the request JSON exactly as the API validated it (Pydantic models in [`wellbeing/schemas.py`](../services/onboard-api/src/onboard_api/wellbeing/schemas.py)). Field limits live there, not in SQLite.
- **`source`**: origin of the row. `simulated`, `demo` or `simulated:*` mark simulated data (`is_simulated_source`).
- **`quality`**: CHECK `IN ('good','suspect','bad')`. The fusion ignores `bad` and also excludes `suspect` (counted and reported in `data_notices`).

## `checkins`

Daily self-report. One row per astronaut and day; resubmitting the same day replaces it (`PUT /astronauts/{id}/wellbeing/checkins/{day}`).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `astronaut_id` | TEXT | PK (1/2) | | See conventions. |
| `day` | TEXT | PK (2/2) | | Day. API: not in the future. |
| `sleep_hours` | REAL | NOT NULL | | Hours. API: 0 to 24, multiple of 0.5. |
| `sleep_quality` | INTEGER | NOT NULL | | CHECK 0 to 4. 4 = best. |
| `energy` | INTEGER | NOT NULL | | CHECK 0 to 4. 4 = best. |
| `mood` | INTEGER | NOT NULL | | CHECK 0 to 4. 4 = best. |
| `interest` | INTEGER | NOT NULL | | CHECK 0 to 4. 4 = best. |
| `stress` | INTEGER | NOT NULL | | CHECK 0 to 4. **4 = worst.** |
| `crew_connection` | INTEGER | NOT NULL | | CHECK 0 to 4. 4 = best. |
| `comment` | TEXT | NULL | | Private free text. API: up to 500 characters. Personal view only; leaves the ship only if a ground package includes `comments`. |
| `source` | TEXT | NOT NULL | | API default `crew`. |
| `submitted_at` | TEXT | NOT NULL | | Timestamp, set by the server. |

## `signals`

Physiological signals for the fusion (Apple Watch export or simulator). Insert only (`POST /wellbeing/signals`).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | | |
| `astronaut_id` | TEXT | NOT NULL | | |
| `kind` | TEXT | NOT NULL | | App: `hrv_sdnn`, `resting_heart_rate`, `sleep_hours`. No SQL CHECK. |
| `value` | REAL | NOT NULL | | API: ≥ 0. |
| `unit` | TEXT | NOT NULL | | Fixed per kind (API 422 otherwise): `hrv_sdnn` → `ms`, `resting_heart_rate` → `bpm`, `sleep_hours` → `h`. |
| `recorded_at` | TEXT | NOT NULL | | Capture time. For `sleep_hours`, wake-up time (the night counts for that day). |
| `received_at` | TEXT | NOT NULL | | Timestamp, set by the server. |
| `quality` | TEXT | NOT NULL | | See conventions. |
| `source` | TEXT | NOT NULL | | e.g. `apple_watch_export`, `simulated`. |

Index `idx_signals_lookup (astronaut_id, recorded_at)`.

## `vision_sessions`

One camera summary from the vision process: one per daily log (`bitacora`) or one per person and window in ambient mode (`ambiente`). Insert only (`POST /wellbeing/vision-sessions`).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | | |
| `astronaut_id` | TEXT | NOT NULL | | Known id or `unknown-<track>`. |
| `started_at` | TEXT | NOT NULL | | Timestamp, copied from the body for indexing. The session counts for this day. |
| `body` | TEXT | NOT NULL | | `VisionSessionCreate` JSON: `session_type`, `module_id`, `ended_at`, `quality`, `valid_frame_ratio`, `identity`, `neutral_ok`, `fatigue`, `tension`, `motion`, `provisional`. `tension` may carry the optional `brow_lower_peak_1s` and `lip_press_peak_1s` (0-1, highest level held ≥ 1 s); older rows without them read as null, so no migration was needed. `lip_press_*` is stored but not scored: vision now filters speech, but one pressed-lips log is not enough evidence, and as extra stress components the lips would dilute the brow signal. Fields and ranges: contract section 6. |
| `received_at` | TEXT | NOT NULL | | Timestamp, set by the server. |

Index `idx_vision_lookup (astronaut_id, started_at)`.

## `co_presence`

One module window (60 s from the vision process; the simulator uses 30 min). Insert only (`POST /wellbeing/co-presence`).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | | |
| `window_start` | TEXT | NOT NULL | | Timestamp, copied from the body. The window counts for this day. |
| `body` | TEXT | NOT NULL | | `CoPresenceCreate` JSON: `module_id`, `source`, `window_end`, `occupants`, `pairs` (distance in shoulder widths and 2D facing ratio, both approximate), `quality`, `provisional`. |
| `received_at` | TEXT | NOT NULL | | Timestamp, set by the server. |

## `co_presence_members`

Who appears in each window, so per-astronaut queries do not parse JSON.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `window_id` | INTEGER | PK (1/2) | | FK `co_presence(id)` ON DELETE CASCADE. |
| `astronaut_id` | TEXT | PK (2/2) | | One row per occupant, including `unknown-<track>`. |

Index `idx_co_presence_member (astronaut_id)`.

## `ground_packages` (version 2)

Package for the ground psychologist. Created only with the astronaut's explicit consent (`POST /wellbeing/ground-packages`, 422 otherwise), queued on board, never sent automatically.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | PK | | UUID v4, set by the server. |
| `astronaut_id` | TEXT | NOT NULL | | Must be a registered astronaut (404 otherwise). |
| `body` | TEXT | NOT NULL | | `GroundPackageCreate` JSON: `requested_by` (`self`, `captain`, `ground_psychologist`), `requested_by_name`, `consent` (`astronaut_confirmed` true, `statement_version`), `period_from`, `period_to`, `include` (`assessment`, `timeline`, `checkins`, `comments`), `note`. |
| `status` | TEXT | NOT NULL | | CHECK `IN ('queued','withdrawn','sent')`. `queued` on creation; `withdrawn` when the astronaut withdraws consent (content then returns 409); `sent` is reserved for the future telemetry link. |
| `consent_recorded_at` | TEXT | NOT NULL | | Timestamp of the consent (creation time). |
| `created_at` | TEXT | NOT NULL | | Timestamp. |
| `updated_at` | TEXT | NOT NULL | | Timestamp of the last status change. |

Index `idx_ground_packages_astronaut (astronaut_id, created_at)`.

## Version and migrations (wellbeing)

- Same runner as onboard: `init_db(db_path, migrations_dir=WELLBEING_MIGRATIONS_DIR)` in [`wellbeing/database.py`](../services/onboard-api/src/onboard_api/wellbeing/database.py), with `db/migrations/wellbeing` resolved from the package location. Same rules: one transaction per file together with its `PRAGMA user_version`, rerun is a no-op, newer databases are rejected, `PRAGMA foreign_key_check` after migrating.
- The onboard app's start-up is not changed: the module migrates lazily on its first connection, once per process and path.
- Versions: `0001_baseline.sql` = 1 (inputs), `0002_ground_packages.sql` = 2. A `wellbeing.db` at version 1 gets only 0002 and keeps its rows.
