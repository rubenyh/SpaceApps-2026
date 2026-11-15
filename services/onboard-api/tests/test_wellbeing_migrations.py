import sqlite3
from pathlib import Path

from onboard_api.repositories.database import init_db, load_migrations
from onboard_api.wellbeing.database import WELLBEING_MIGRATIONS_DIR, connect_wellbeing

LATEST = len(load_migrations(WELLBEING_MIGRATIONS_DIR))


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


def test_new_database_gets_every_migration(tmp_path: Path) -> None:
    db = tmp_path / "new" / "wellbeing.db"
    connect_wellbeing(db).close()
    assert LATEST == 2
    assert version(db) == LATEST
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"checkins", "signals", "vision_sessions", "co_presence",
            "co_presence_members", "ground_packages"} <= tables


def test_rerun_changes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "wellbeing.db"
    connect_wellbeing(db).close()
    before = dump(db)
    # Bypass the per-process lazy cache: run the runner again on the same file.
    init_db(db, migrations_dir=WELLBEING_MIGRATIONS_DIR)
    assert dump(db) == before
    assert version(db) == LATEST


def test_existing_v1_copy_upgrades_and_keeps_data(tmp_path: Path) -> None:
    # A wellbeing.db as v1 left it: the 0001 schema, user_version 1, real rows.
    db = tmp_path / "copy" / "wellbeing.db"
    db.parent.mkdir()
    baseline = (WELLBEING_MIGRATIONS_DIR / "0001_baseline.sql").read_text("utf-8")
    conn = sqlite3.connect(db, isolation_level=None)
    conn.executescript(baseline + "\nPRAGMA user_version = 1;")
    conn.execute(
        "INSERT INTO checkins VALUES ('ast-01', '2026-11-10', 7.5, 3, 3, 3, 3, 1, 3,"
        " 'privado', 'crew', '2026-11-10T21:00:00.000000Z')"
    )
    conn.execute(
        "INSERT INTO signals (astronaut_id, kind, value, unit, recorded_at, received_at,"
        " quality, source) VALUES ('ast-01', 'hrv_sdnn', 50, 'ms',"
        " '2026-11-10T07:00:00.000000Z', '2026-11-10T07:00:00.000000Z', 'good', 'watch')"
    )
    conn.close()
    before = [line for line in dump(db) if "INSERT" in line]

    connect_wellbeing(db).close()

    assert version(db) == LATEST
    after = dump(db)
    assert all(line in after for line in before)
    assert any("ground_packages" in line for line in after)
