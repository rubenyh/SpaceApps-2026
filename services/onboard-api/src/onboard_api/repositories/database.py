"""SQLite connection handling, schema setup and timestamp encoding."""

import sqlite3
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

SCHEMA_VERSION = 1

# Fixed width so lexicographic order in SQL equals chronological order.
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# Sensor configuration created together with the schema. All rows are
# provisional. Columns: kind, unit, stale_after_seconds, normal_min,
# normal_max, range_role, range_source.
_SEED_SENSOR_CONFIG = [
    ("heart_rate", "bpm", 300, 60, 100, "health", "AHA / Mayo Clinic"),
    ("spo2", "%", 300, 95, 100, "health", "Mayo Clinic"),
    ("muscle_density", None, 604800, None, None, "health", None),
    ("urine_ph", "pH", 86400, 4.6, 8.0, "health", "MedlinePlus"),
    ("urine_salinity", None, 86400, None, None, "health", None),
    ("urine_color", "rgb_hex", 86400, None, None, "health", None),
    ("urine_temperature", "°C", 86400, 32, 38, "sample_validity", "49 CFR 40.65"),
    ("urine_radiation_marker", None, 86400, None, None, "health", None),
]


def to_db_timestamp(value: datetime) -> str:
    """Encode an aware datetime as a UTC fixed-width ISO 8601 string."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)


def from_db_timestamp(value: str) -> datetime:
    return datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection in autocommit mode with the required pragmas.

    check_same_thread=False because FastAPI may open the connection in one
    worker thread and run the endpoint in another. Each connection is still
    used by one request at a time and closed when the request ends.
    """
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path, now: datetime) -> None:
    """Create the parent directory, then the schema and seed if user_version is 0."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise RuntimeError(
                f"unsupported database schema version {version} in {db_path}; "
                f"expected {SCHEMA_VERSION}"
            )
        script = files("onboard_api.repositories").joinpath("schema.sql").read_text("utf-8")
        try:
            # BEGIN goes inside the script because executescript commits any
            # transaction that is already open before running.
            conn.executescript("BEGIN;\n" + script)
            updated_at = to_db_timestamp(now)
            conn.executemany(
                "INSERT INTO sensor_config (kind, unit, stale_after_seconds, normal_min,"
                " normal_max, range_role, provisional, range_source, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                [(*row, updated_at) for row in _SEED_SENSOR_CONFIG],
            )
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
