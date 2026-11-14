# Data dictionary: onboard database

SQLite database of `services/onboard-api` (`ONBOARD_DB_PATH`, default `data/onboard.db`, relative to the working directory, git-ignored). `ground-api` has no database.

Schema and reference data: [`migrations/onboard/0001_baseline.sql`](migrations/onboard/0001_baseline.sql). If this document and the SQL differ, the SQL wins.

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
| `source` | TEXT | NOT NULL | | Origin, e.g. `manual`, `serial:pulse`. API: 1 to 64 characters. |

Table CHECK `(value IS NULL) <> (value_text IS NULL)`: exactly one of `value` and `value_text` is set. The API checks the same rule before inserting (422).

### Kind and unit checks

- `kind REFERENCES sensor_config(kind)` is enforced: `connect()` runs `PRAGMA foreign_keys = ON` on every connection (SQLite leaves it off by default). The same applies to `astronaut_id`.
- The API first validates `kind` against `SensorKind` (422 for other values).
- `record_reading` in [`services/readings.py`](../services/onboard-api/src/onboard_api/services/readings.py) then loads the `sensor_config` row: `unit` must match exactly when the configured unit is not NULL (otherwise 422); a NULL configured unit accepts any unit. A missing row raises a server error, because every `SensorKind` is seeded.

### Index

`idx_readings_lookup ON readings (astronaut_id, kind, recorded_at DESC)`: serves "latest reading of one kind" (`ReadingRepository.latest`) and the filtered, newest-first list (`ReadingRepository.search`).

## Freshness

`stale_after_seconds` is read in two places, with different edge rules:

| | `GET /astronauts/{id}/status` ([`services/status.py`](../services/onboard-api/src/onboard_api/services/status.py)) | Assistant `SqliteReadingsProvider` ([`assistant/workflows/medical/context.py`](../services/onboard-api/src/onboard_api/assistant/workflows/medical/context.py)) |
|---|---|---|
| Age | `now - recorded_at`, clamped to 0. | Same, clamped to 0. |
| Stale when | `age > stale_after_seconds`. | `age > stale_after_seconds`, or `recorded_at` more than 5 s in the future (`FUTURE_SKEW_SECONDS`; also adds a future-capture warning). |
| `stale_after_seconds` NULL | Never stale. | Never stale (future rule still applies). |
| No `sensor_config` row | Kind not listed (rows come from `sensor_config`). | Uses 300 s (`DEFAULT_STALE_AFTER_SECONDS`). |
| Future `recorded_at` | Only clamped: age 0, evaluated normally. | Stale beyond the 5 s skew. |

## Version and migrations

- Schema version is `PRAGMA user_version`. Migration files are `db/migrations/onboard/NNNN_<slug>.sql`; `NNNN` is the `user_version` the database has after that file. `0001_baseline.sql` is version 1.
- `init_db` in [`database.py`](../services/onboard-api/src/onboard_api/repositories/database.py) runs at service start-up. Each pending migration runs in one transaction together with its `PRAGMA user_version = N`; on error it rolls back, leaving schema and version unchanged. Rerunning is a no-op. A database newer than the latest file is rejected.
- Legacy databases (version 0 with the tables already present) are compared with the 0001 schema; on a match only `user_version` is set to 1 (no data change), otherwise start-up fails naming the difference.
- After migrating, `PRAGMA foreign_key_check` must report no violations, or start-up fails.
- Migrations directory: resolved from the package location by default; override with `ONBOARD_MIGRATIONS_DIR`.
- New schema change: add the next numbered file. Never edit an applied migration.
