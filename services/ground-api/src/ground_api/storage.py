"""Ground SQLite store. The only module that writes SQL."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

from ground_api.schemas import (
    Alert,
    Astronaut,
    BatchAccepted,
    GroundAcknowledgment,
    GroundIncident,
    GroundIncidentUpdate,
    GroundReading,
    IncidentUpdate,
    Link,
    SensorConfig,
    SensorKind,
    TelemetryBatch,
)
from ground_api.status import alert_side

KIND_ORDER = {kind: index for index, kind in enumerate(get_args(SensorKind))}

# Fixed width so lexicographic order in SQL equals chronological order.
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# shortcut: astronauts and sensors are keyed without ship_id (one ship in the demo);
# add ship_id to their keys if ground ever serves several ships.
SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    ship_id TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS astronauts (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sensors (
    kind TEXT PRIMARY KEY,
    unit TEXT,
    stale_after_seconds INTEGER,
    normal_min REAL,
    normal_max REAL,
    range_role TEXT NOT NULL,
    provisional INTEGER NOT NULL,
    range_source TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    ship_id TEXT NOT NULL,
    id INTEGER NOT NULL,
    astronaut_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    value REAL,
    value_text TEXT,
    unit TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    quality TEXT NOT NULL,
    source TEXT NOT NULL,
    ground_received_at TEXT NOT NULL,
    PRIMARY KEY (ship_id, id)
);
CREATE INDEX IF NOT EXISTS readings_by_astronaut
    ON readings (astronaut_id, kind, recorded_at);
CREATE TABLE IF NOT EXISTS alerts (
    ship_id TEXT NOT NULL,
    reading_id INTEGER NOT NULL,
    normal_min REAL,
    normal_max REAL,
    side TEXT NOT NULL,
    PRIMARY KEY (ship_id, reading_id)
);
CREATE TABLE IF NOT EXISTS incidents (
    ship_id TEXT NOT NULL,
    id TEXT NOT NULL,
    astronaut_id TEXT,
    began_at TEXT,
    urgency TEXT NOT NULL,
    protocol_id TEXT,
    protocol_version TEXT,
    matched_rules_json TEXT NOT NULL,
    action TEXT,
    PRIMARY KEY (ship_id, id)
);
CREATE TABLE IF NOT EXISTS incident_updates (
    ship_id TEXT NOT NULL,
    id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    acknowledged_by TEXT,
    received_at TEXT NOT NULL,
    PRIMARY KEY (ship_id, id)
);
CREATE INDEX IF NOT EXISTS incident_updates_by_incident
    ON incident_updates (ship_id, incident_id, occurred_at);
"""

_READING_COLUMNS = (
    "r.id, r.astronaut_id, r.kind, r.value, r.value_text, r.unit, r.recorded_at,"
    " r.received_at, r.quality, r.source, r.ground_received_at"
)


def to_db(value: datetime) -> str:
    return value.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)


def from_db(value: str) -> datetime:
    return datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def _to_reading(row: sqlite3.Row) -> GroundReading:
    return GroundReading(
        id=row["id"],
        astronaut_id=row["astronaut_id"],
        kind=row["kind"],
        value=row["value"],
        value_text=row["value_text"],
        unit=row["unit"],
        recorded_at=from_db(row["recorded_at"]),
        received_at=from_db(row["received_at"]),
        quality=row["quality"],
        source=row["source"],
        ground_received_at=from_db(row["ground_received_at"]),
    )


def list_sensors(conn: sqlite3.Connection) -> list[SensorConfig]:
    """Configs in SensorKind order."""
    rows = conn.execute("SELECT * FROM sensors").fetchall()
    configs = [SensorConfig(**{**dict(row), "provisional": bool(row["provisional"])}) for row in rows]
    return sorted(configs, key=lambda c: KIND_ORDER[c.kind])


def ingest(conn: sqlite3.Connection, batch: TelemetryBatch, now: datetime) -> BatchAccepted:
    """Store one batch atomically: readings by (ship_id, id), incident updates by (ship_id, id)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        inserted = conn.execute(
            "INSERT INTO batches (batch_id, ship_id, sent_at, received_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (batch_id) DO NOTHING",
            (str(batch.batch_id), batch.ship_id, to_db(batch.sent_at), to_db(now)),
        ).rowcount
        if not inserted:  # retried batch already stored
            conn.execute("ROLLBACK")
            return BatchAccepted(
                accepted=0,
                duplicates=len(batch.readings),
                incident_updates_duplicates=len(batch.incident_updates),
            )
        conn.executemany(
            "INSERT INTO astronauts (id, display_name) VALUES (?, ?)"
            " ON CONFLICT (id) DO UPDATE SET display_name = excluded.display_name",
            [(a.id, a.display_name) for a in batch.astronauts],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO sensors (kind, unit, stale_after_seconds, normal_min,"
            " normal_max, range_role, provisional, range_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (s.kind, s.unit, s.stale_after_seconds, s.normal_min, s.normal_max,
                 s.range_role, int(s.provisional), s.range_source)
                for s in batch.sensors
            ],
        )
        configs = {c.kind: c for c in list_sensors(conn)}
        accepted = 0
        for r in batch.readings:
            if not conn.execute(
                "INSERT INTO readings (ship_id, id, astronaut_id, kind, value, value_text, unit,"
                " recorded_at, received_at, quality, source, ground_received_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (batch.ship_id, r.id, r.astronaut_id, r.kind, r.value, r.value_text, r.unit,
                 to_db(r.recorded_at), to_db(r.received_at), r.quality, r.source, to_db(now)),
            ).rowcount:
                continue
            accepted += 1
            config = configs.get(r.kind)
            side = alert_side(config, r)
            if side:
                conn.execute(
                    "INSERT INTO alerts (ship_id, reading_id, normal_min, normal_max, side)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (batch.ship_id, r.id, config.normal_min, config.normal_max, side),
                )
        updates_accepted = sum(
            _ingest_incident_update(conn, batch.ship_id, u, now) for u in batch.incident_updates
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return BatchAccepted(
        accepted=accepted,
        duplicates=len(batch.readings) - accepted,
        incident_updates_accepted=updates_accepted,
        incident_updates_duplicates=len(batch.incident_updates) - updates_accepted,
    )


def _ingest_incident_update(
    conn: sqlite3.Connection, ship_id: str, u: IncidentUpdate, now: datetime
) -> bool:
    """Store an update once per (ship_id, id) and upsert its incident. True if new."""
    if not conn.execute(
        "INSERT INTO incident_updates (ship_id, id, incident_id, type, occurred_at,"
        " acknowledged_by, received_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        (ship_id, u.id, u.incident_id, u.type, to_db(u.occurred_at), u.acknowledged_by, to_db(now)),
    ).rowcount:
        return False
    # began_at comes only from the created update; the summary takes the latest values.
    conn.execute(
        "INSERT INTO incidents (ship_id, id, astronaut_id, began_at, urgency, protocol_id,"
        " protocol_version, matched_rules_json, action) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (ship_id, id) DO UPDATE SET astronaut_id = excluded.astronaut_id,"
        " began_at = coalesce(incidents.began_at, excluded.began_at), urgency = excluded.urgency,"
        " protocol_id = excluded.protocol_id, protocol_version = excluded.protocol_version,"
        " matched_rules_json = excluded.matched_rules_json, action = excluded.action",
        (
            ship_id, u.incident_id, u.astronaut_id,
            to_db(u.occurred_at) if u.type == "created" else None,
            u.urgency, u.protocol_id, u.protocol_version,
            json.dumps([r.model_dump() for r in u.matched_rules], ensure_ascii=False), u.action,
        ),
    )
    return True


def last_reading_id(conn: sqlite3.Connection, ship_id: str) -> int | None:
    return conn.execute("SELECT max(id) FROM readings WHERE ship_id = ?", (ship_id,)).fetchone()[0]


def link(conn: sqlite3.Connection, now: datetime) -> Link:
    last = conn.execute(
        "SELECT ship_id, sent_at, received_at FROM batches ORDER BY received_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    batches = conn.execute("SELECT count(*) FROM batches").fetchone()[0]
    readings = conn.execute("SELECT count(*) FROM readings").fetchone()[0]
    received = from_db(last["received_at"]) if last else None
    return Link(
        ship_id=last["ship_id"] if last else None,
        last_batch_sent_at=from_db(last["sent_at"]) if last else None,
        last_batch_received_at=received,
        seconds_since_last_batch=max(0, int((now - received).total_seconds())) if received else None,
        batches_received=batches,
        readings_received=readings,
    )


def list_astronauts(conn: sqlite3.Connection) -> list[Astronaut]:
    rows = conn.execute("SELECT id, display_name FROM astronauts ORDER BY id").fetchall()
    return [Astronaut(id=row["id"], display_name=row["display_name"]) for row in rows]


def astronaut_exists(conn: sqlite3.Connection, astronaut_id: str) -> bool:
    return conn.execute("SELECT 1 FROM astronauts WHERE id = ?", (astronaut_id,)).fetchone() is not None


def latest_reading(conn: sqlite3.Connection, astronaut_id: str, kind: str) -> GroundReading | None:
    row = conn.execute(
        f"SELECT {_READING_COLUMNS} FROM readings r WHERE astronaut_id = ? AND kind = ?"
        " ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (astronaut_id, kind),
    ).fetchone()
    return _to_reading(row) if row else None


def search_readings(
    conn: sqlite3.Connection,
    astronaut_id: str,
    kind: str | None,
    since: datetime | None,
    limit: int,
) -> list[GroundReading]:
    clauses, params = ["astronaut_id = ?"], [astronaut_id]
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if since is not None:
        clauses.append("recorded_at >= ?")
        params.append(to_db(since))
    rows = conn.execute(
        f"SELECT {_READING_COLUMNS} FROM readings r WHERE {' AND '.join(clauses)}"
        " ORDER BY recorded_at DESC, id DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    return [_to_reading(row) for row in rows]


def list_alerts(conn: sqlite3.Connection, limit: int) -> list[Alert]:
    rows = conn.execute(
        f"SELECT {_READING_COLUMNS}, a.normal_min AS a_min, a.normal_max AS a_max, a.side"
        " FROM alerts a JOIN readings r ON r.ship_id = a.ship_id AND r.id = a.reading_id"
        " ORDER BY r.recorded_at DESC, r.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        Alert(reading=_to_reading(row), normal_min=row["a_min"], normal_max=row["a_max"], side=row["side"])
        for row in rows
    ]


def _to_incident(conn: sqlite3.Connection, row: sqlite3.Row) -> GroundIncident:
    updates = [
        GroundIncidentUpdate(
            id=u["id"],
            type=u["type"],
            occurred_at=from_db(u["occurred_at"]),
            received_at=from_db(u["received_at"]),
            acknowledged_by=u["acknowledged_by"],
        )
        for u in conn.execute(
            "SELECT * FROM incident_updates WHERE ship_id = ? AND incident_id = ?"
            " ORDER BY occurred_at, rowid",
            (row["ship_id"], row["id"]),
        )
    ]
    return GroundIncident(
        ship_id=row["ship_id"],
        id=row["id"],
        astronaut_id=row["astronaut_id"],
        began_at=from_db(row["began_at"]) if row["began_at"] else None,
        urgency=row["urgency"],
        protocol_id=row["protocol_id"],
        protocol_version=row["protocol_version"],
        matched_rules=json.loads(row["matched_rules_json"]),
        action=row["action"],
        acknowledgments=[
            GroundAcknowledgment(
                acknowledged_by=u.acknowledged_by, acknowledged_at=u.occurred_at, received_at=u.received_at
            )
            for u in updates
            if u.type == "acknowledged" and u.acknowledged_by
        ],
        updates=updates,
    )


def list_incidents(conn: sqlite3.Connection) -> list[GroundIncident]:
    """Newest began_at first; incidents whose created update has not arrived last."""
    rows = conn.execute(
        "SELECT * FROM incidents ORDER BY began_at IS NULL, began_at DESC, rowid DESC"
    ).fetchall()
    return [_to_incident(conn, row) for row in rows]


def get_incident(conn: sqlite3.Connection, incident_id: str) -> GroundIncident | None:
    # One ship in the demo: if two ships share an id, the first stored wins.
    row = conn.execute(
        "SELECT * FROM incidents WHERE id = ? ORDER BY rowid LIMIT 1", (incident_id,)
    ).fetchone()
    return _to_incident(conn, row) if row else None
