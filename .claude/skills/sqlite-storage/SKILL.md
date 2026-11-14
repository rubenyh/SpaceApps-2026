---
name: sqlite-storage
description: Design or change the onboard SQLite monitoring repository that stores astronaut readings. Use when adding tables, queries, migrations, or when workflows/collectors/telemetry need reading data.
---

# SQLite monitoring repository (planned)

Status: not in the repo yet. Use stdlib `sqlite3`; add an ORM only if a real need appears.

## Where
- Planned: `services/onboard-api/src/onboard_api/storage/` - `repository.py` (queries), `schema.sql` (DDL).
- DB file path from settings (for example `ONBOARD_DB_PATH`, default `data/onboard.db`). Keep the DB file out of git.

## Do
- One repository module owns all SQL. Collectors write through it. The assistant and telemetry read through it.
- Every reading row has `astronaut_id`, `kind` (for example `heart_rate`, `spo2`, `posture`), `value`, `unit`, `recorded_at` (UTC ISO 8601), `source`.
- Repository reads return typed objects (dataclass or Pydantic) and an empty list when nothing matches. Never invent defaults; consumers decide what "missing" means.
- Staleness is decided by the caller from `recorded_at` and a configured max age, not inside SQL.
- Open connections per request or per thread (`sqlite3` objects are not thread-safe across threads by default). Enable `PRAGMA journal_mode=WAL` so collectors can write while the API reads.
- Use parameterized queries only.
- Schema changes: additive `ALTER TABLE` plus a `PRAGMA user_version` bump, applied at startup.

## Verify
- Tests against a temp-file DB (`tmp_path`), not the real DB: insert, latest-per-kind, empty result.
- `uv run pytest` from `services/onboard-api` (after `uv add --dev pytest`).

Docs: https://docs.python.org/3.12/library/sqlite3.html , https://www.sqlite.org/wal.html
