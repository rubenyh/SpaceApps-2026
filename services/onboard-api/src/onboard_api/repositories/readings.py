import sqlite3
from datetime import datetime

from onboard_api.repositories.database import from_db_timestamp, to_db_timestamp
from onboard_api.schemas.readings import Reading, ReadingCreate
from onboard_api.schemas.sensors import SensorKind

_COLUMNS = (
    "id, astronaut_id, kind, value, value_text, unit, recorded_at, received_at,"
    " quality, source"
)


def _to_reading(row: sqlite3.Row) -> Reading:
    return Reading(
        id=row["id"],
        astronaut_id=row["astronaut_id"],
        kind=row["kind"],
        value=row["value"],
        value_text=row["value_text"],
        unit=row["unit"],
        recorded_at=from_db_timestamp(row["recorded_at"]),
        received_at=from_db_timestamp(row["received_at"]),
        quality=row["quality"],
        source=row["source"],
    )


class ReadingRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, data: ReadingCreate, received_at: datetime) -> Reading:
        cursor = self._conn.execute(
            "INSERT INTO readings (astronaut_id, kind, value, value_text, unit,"
            " recorded_at, received_at, quality, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.astronaut_id,
                data.kind,
                data.value,
                data.value_text,
                data.unit,
                to_db_timestamp(data.recorded_at),
                to_db_timestamp(received_at),
                data.quality,
                data.source,
            ),
        )
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM readings WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _to_reading(row)

    def search(
        self,
        astronaut_id: str,
        kind: SensorKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[Reading]:
        """Readings newest first by recorded_at. since/until are inclusive."""
        clauses = ["astronaut_id = ?"]
        params: list[object] = [astronaut_id]
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if since is not None:
            clauses.append("recorded_at >= ?")
            params.append(to_db_timestamp(since))
        if until is not None:
            clauses.append("recorded_at <= ?")
            params.append(to_db_timestamp(until))
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM readings WHERE {' AND '.join(clauses)}"
            " ORDER BY recorded_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        return [_to_reading(row) for row in rows]

    def latest(self, astronaut_id: str, kind: SensorKind) -> Reading | None:
        """Most recent reading of one kind by recorded_at, or None."""
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM readings WHERE astronaut_id = ? AND kind = ?"
            " ORDER BY recorded_at DESC, id DESC LIMIT 1",
            (astronaut_id, kind),
        ).fetchone()
        return _to_reading(row) if row else None
