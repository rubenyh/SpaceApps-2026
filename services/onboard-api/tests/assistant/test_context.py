from datetime import UTC, datetime, timedelta

from onboard_api.assistant.workflows.medical.context import SqliteReadingsProvider
from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.database import connect, init_db
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.schemas.astronauts import AstronautCreate
from onboard_api.schemas.readings import ReadingCreate

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _setup(tmp_path, readings: dict[str, timedelta], sql: str = ""):
    """DB with astronaut 'ana' and one reading per kind, recorded at NOW - offset."""
    db = tmp_path / "onboard.db"
    init_db(db, NOW)
    conn = connect(db)
    AstronautRepository(conn).create(AstronautCreate(id="ana", display_name="Ana"), NOW)
    repo = ReadingRepository(conn)
    for kind, offset in readings.items():
        repo.create(
            ReadingCreate(astronaut_id="ana", kind=kind, value=80, unit="x", quality="good",
                          recorded_at=NOW - offset, source="test"),
            NOW,
        )
    if sql:
        # readings.kind references sensor_config; drop the FK check to simulate a missing row.
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(sql)
    conn.commit()
    conn.close()
    return SqliteReadingsProvider(db).load("ana", NOW)


def test_missing_config_row_defaults_to_300s(tmp_path) -> None:
    ctx = _setup(
        tmp_path,
        {"heart_rate": timedelta(seconds=301), "spo2": timedelta(seconds=299)},
        "DELETE FROM sensor_config WHERE kind IN ('heart_rate', 'spo2')",
    )
    assert ctx.latest["heart_rate"].stale
    assert not ctx.latest["spo2"].stale
    assert any("pulse" in w and "valid for 300 s" in w for w in ctx.warnings)


def test_explicit_null_config_is_never_stale(tmp_path) -> None:
    ctx = _setup(
        tmp_path,
        {"heart_rate": timedelta(days=2)},
        "UPDATE sensor_config SET stale_after_seconds = NULL WHERE kind = 'heart_rate'",
    )
    assert not ctx.latest["heart_rate"].stale


def test_future_reading_within_skew_is_fresh(tmp_path) -> None:
    ctx = _setup(tmp_path, {"heart_rate": timedelta(seconds=-5)})
    hr = ctx.latest["heart_rate"]
    assert not hr.stale and hr.age_seconds == 0
    assert not any("future" in w for w in ctx.warnings)


def test_future_reading_beyond_skew_is_flagged_stale(tmp_path) -> None:
    ctx = _setup(tmp_path, {"heart_rate": timedelta(minutes=-10)})
    assert ctx.latest["heart_rate"].stale
    assert any("pulse" in w and "capture time in the future" in w for w in ctx.warnings)
