---
name: sqlite-storage
description: Design or change the onboard SQLite monitoring repository that stores astronaut readings. Use when adding tables, queries, migrations, or when workflows/collectors/telemetry need reading data.
---

# SQLite monitoring repository

Status: implemented with stdlib `sqlite3`. Schema reference: `db/data-dictionary.md`. Add an ORM only if a real need appears.

## Where
- Queries: `services/onboard-api/src/onboard_api/repositories/*.py`. Connections and migration runner: `repositories/database.py`.
- DDL and schema reference rows: `db/migrations/onboard/NNNN_<slug>.sql` (one canonical copy; NNNN = resulting `PRAGMA user_version`).
- DB file path from settings (for example `ONBOARD_DB_PATH`, default `data/onboard.db`). Keep the DB file out of git.

## Do
- One repository module owns all SQL. Collectors write through it. The assistant and telemetry read through it.
- Every reading row has `astronaut_id`, `kind` (for example `heart_rate`, `spo2`, `posture`), `value`, `unit`, `recorded_at` (UTC ISO 8601), `source`.
- Repository reads return typed objects (dataclass or Pydantic) and an empty list when nothing matches. Never invent defaults; consumers decide what "missing" means.
- Staleness is decided by the caller from `recorded_at` and a configured max age, not inside SQL.
- Open connections per request or per thread (`sqlite3` objects are not thread-safe across threads by default). Enable `PRAGMA journal_mode=WAL` so collectors can write while the API reads.
- Use parameterized queries only.
- Schema changes: add the next `db/migrations/onboard/NNNN_<slug>.sql`; never edit an applied migration. The runner applies each file and its `user_version` in one transaction at startup. Update `db/data-dictionary.md` in the same PR.

## Verify
- Tests against a temp-file DB (`tmp_path`), not the real DB: insert, latest-per-kind, empty result.
- `uv run pytest` from `services/onboard-api` (`tests/test_migrations.py` covers fresh, upgrade, rerun and rollback).

Docs: https://docs.python.org/3.12/library/sqlite3.html , https://www.sqlite.org/wal.html
