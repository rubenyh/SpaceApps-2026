import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from onboard_api.repositories.database import (
    MIGRATIONS_DIR,
    _schema,
    connect,
    init_db,
)

BASELINE = MIGRATIONS_DIR / "0001_baseline.sql"
INCIDENTS = MIGRATIONS_DIR / "0002_incidents.sql"
ORIGIN = MIGRATIONS_DIR / "0003_incident_origin.sql"
LATEST = 3
REPO_ROOT = MIGRATIONS_DIR.parents[2]
# Last main commit before the move to db/migrations.
OLD_SCHEMA_REF = "2d157f7:services/onboard-api/src/onboard_api/repositories/schema.sql"
OLD_SEED = [
    ("heart_rate", "bpm", 300, 60, 100, "health", "AHA / Mayo Clinic"),
    ("spo2", "%", 300, 95, 100, "health", "Mayo Clinic"),
    ("muscle_density", None, 604800, None, None, "health", None),
    ("urine_ph", "pH", 86400, 4.6, 8.0, "health", "MedlinePlus"),
    ("urine_salinity", None, 86400, None, None, "health", None),
    ("urine_color", "rgb_hex", 86400, None, None, "health", None),
    ("urine_temperature", "°C", 86400, 32, 38, "sample_validity", "49 CFR 40.65"),
    ("urine_radiation_marker", None, 86400, None, None, "health", None),
]
# Pre-migrations schema.sql (deleted in this change), kept for legacy-DB tests.
_body = BASELINE.read_text("utf-8")
LEGACY_DDL = _body[: _body.index("INSERT INTO sensor_config")]


def version(db: Path) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def dump(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


def schema_of(script: str) -> dict:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(script)
    return _schema(conn)


def make_legacy(db: Path, user_version: int, ddl: str = LEGACY_DDL) -> None:
    """A DB as the old init_db left it: schema, seed, then user data."""
    conn = sqlite3.connect(db, isolation_level=None)
    conn.executescript(ddl + f"\nPRAGMA user_version = {user_version};")
    conn.executemany(
        "INSERT INTO sensor_config (kind, unit, stale_after_seconds, normal_min, normal_max,"
        " range_role, provisional, range_source, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?, '2026-01-01T00:00:00.000000Z')",
        OLD_SEED,
    )
    conn.execute("UPDATE sensor_config SET stale_after_seconds = 60 WHERE kind = 'spo2'")
    conn.execute("INSERT INTO astronauts VALUES ('ana', 'Ana', '2026-01-01T00:00:00.000000Z')")
    conn.execute(
        "INSERT INTO readings (astronaut_id, kind, value, unit, recorded_at, received_at,"
        " quality, source) VALUES ('ana', 'heart_rate', 72, 'bpm',"
        " '2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:01.000000Z', 'good', 'manual')"
    )
    conn.close()


def test_fresh_db_gets_baseline(tmp_path: Path) -> None:
    db = tmp_path / "new" / "onboard.db"
    init_db(db)
    assert version(db) == LATEST
    conn = connect(db)
    rows = conn.execute("SELECT * FROM sensor_config ORDER BY rowid").fetchall()
    assert [tuple(r)[:6] + (r["range_source"],) for r in rows] == [
        (k, u, s, mn, mx, role, src) for k, u, s, mn, mx, role, src in OLD_SEED
    ]
    assert all(r["provisional"] == 1 and len(r["updated_at"]) == 27 for r in rows)
    assert _schema(conn) == schema_of(LEGACY_DDL + INCIDENTS.read_text("utf-8") + ORIGIN.read_text("utf-8"))
    assert conn.execute("SELECT count(*) FROM incidents").fetchone()[0] == 0
    conn.close()


def test_baseline_matches_old_schema_sql_on_main() -> None:
    try:
        old = subprocess.run(
            ["git", "show", OLD_SCHEMA_REF], cwd=REPO_ROOT, capture_output=True,
            check=True, encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("old schema.sql at 2d157f7 not available")
    assert schema_of(old) == schema_of(BASELINE.read_text("utf-8"))


def test_rerun_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    init_db(db)
    before = dump(db)
    init_db(db)
    assert dump(db) == before and version(db) == LATEST


def incident_tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'incident%'")}
    finally:
        conn.close()


def test_version_1_db_gets_0002_and_keeps_data(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    make_legacy(db, user_version=1)
    before = dump(db)
    init_db(db)
    assert version(db) == LATEST
    assert set(before) <= set(dump(db))  # every existing row and table kept
    assert incident_tables(db) == {"incidents", "incident_events"}
    conn = connect(db)
    assert _schema(conn) == schema_of(LEGACY_DDL + INCIDENTS.read_text("utf-8") + ORIGIN.read_text("utf-8"))
    conn.close()


def test_legacy_version_0_is_baselined(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    make_legacy(db, user_version=0)
    before = dump(db)
    init_db(db)
    assert version(db) == LATEST
    assert set(before) <= set(dump(db))  # iterdump excludes user_version: data and config intact


def test_legacy_version_0_mismatch_fails(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    make_legacy(db, 0, LEGACY_DDL.replace("source       TEXT NOT NULL,", "source TEXT,"))
    before = dump(db)
    with pytest.raises(RuntimeError, match="readings"):
        init_db(db)
    assert dump(db) == before and version(db) == 0


def test_real_db_copy(tmp_path: Path) -> None:
    real = Path(__file__).parents[1] / "data" / "onboard.db"
    if not real.is_file():
        pytest.skip("no local data/onboard.db")
    db = tmp_path / "onboard.db"
    shutil.copy(real, db)  # never touch the original
    before = dump(db)
    init_db(db)
    assert set(before) <= set(dump(db)) and version(db) == LATEST


def migrations(tmp_path: Path, **extra: str) -> Path:
    folder = tmp_path / "migrations"
    folder.mkdir()
    shutil.copy(BASELINE, folder)
    shutil.copy(INCIDENTS, folder)
    shutil.copy(ORIGIN, folder)
    for name, sql in extra.items():
        (folder / f"{name}.sql").write_text(sql, "utf-8")
    return folder


def test_failing_migration_rolls_back(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    init_db(db)
    before = dump(db)
    folder = migrations(
        tmp_path,
        **{"0004_broken": "CREATE TABLE extra (id INTEGER);\nINSERT INTO nope VALUES (1);"},
    )
    for _ in range(2):  # next run fails cleanly too
        with pytest.raises(sqlite3.OperationalError):
            init_db(db, migrations_dir=folder)
        assert dump(db) == before and version(db) == LATEST


def test_successful_migration_applied_with_version(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    init_db(db)
    folder = migrations(tmp_path, **{"0004_add_note": "ALTER TABLE readings ADD COLUMN note TEXT;"})
    init_db(db, migrations_dir=folder)
    assert version(db) == 4
    conn = connect(db)
    assert "note" in [r["name"] for r in conn.execute("PRAGMA table_info(readings)")]
    conn.close()


def test_newer_db_than_code_fails(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 5")
    conn.close()
    before = dump(db)
    with pytest.raises(RuntimeError, match="newer"):
        init_db(db)
    assert dump(db) == before and version(db) == 5


def test_gap_or_missing_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not found"):
        init_db(tmp_path / "a.db", migrations_dir=tmp_path / "missing")
    folder = migrations(tmp_path, **{"0005_gap": "SELECT 1;"})
    with pytest.raises(RuntimeError, match="1..N"):
        init_db(tmp_path / "b.db", migrations_dir=folder)


def test_foreign_key_violation_fails(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    init_db(db)
    conn = sqlite3.connect(db)  # foreign_keys off by default
    conn.execute(
        "INSERT INTO readings (astronaut_id, kind, value, unit, recorded_at, received_at,"
        " quality, source) VALUES ('ghost', 'heart_rate', 72, 'bpm',"
        " '2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:01.000000Z', 'good', 'manual')"
    )
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="readings: 1"):
        init_db(db)


def test_version_2_incident_gets_origin_defaults(tmp_path: Path) -> None:
    db = tmp_path / "onboard.db"
    folder = tmp_path / "v2"
    folder.mkdir()
    shutil.copy(BASELINE, folder)
    shutil.copy(INCIDENTS, folder)
    init_db(db, migrations_dir=folder)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO incidents (id, trigger_key, began_at, urgency, steps_json,"
        " matched_rules_json, findings_json, data_notices_json, mission_procedures_json,"
        " missing_guidance_json) VALUES ('old', 'k', '2026-01-01T00:00:00.000000Z',"
        " 'immediate', '[]', '[]', '[]', '[]', '[]', '[]')"
    )
    conn.commit()
    conn.close()
    init_db(db)
    assert version(db) == LATEST
    conn = connect(db)
    row = conn.execute("SELECT reported_via, reading_ids_json FROM incidents").fetchone()
    assert tuple(row) == (None, "[]")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE incidents SET reported_via = 'pager'")
    conn.close()
