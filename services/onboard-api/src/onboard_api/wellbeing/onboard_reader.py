"""Read-only access to the onboard service's tables (owned by the physical side).

Only `astronauts` and `heart_rate` readings are read. Physical readings are
never written here: use POST /readings for that.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from onboard_api.repositories.database import from_db_timestamp


@dataclass(frozen=True)
class AstronautRef:
    id: str
    display_name: str


@dataclass(frozen=True)
class HeartRateReading:
    value: float
    recorded_at: datetime
    quality: str
    source: str


class OnboardReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_astronauts(self) -> list[AstronautRef]:
        rows = self._conn.execute(
            "SELECT id, display_name FROM astronauts ORDER BY id"
        ).fetchall()
        return [AstronautRef(row["id"], row["display_name"]) for row in rows]

    def get_astronaut(self, astronaut_id: str) -> AstronautRef | None:
        row = self._conn.execute(
            "SELECT id, display_name FROM astronauts WHERE id = ?", (astronaut_id,)
        ).fetchone()
        return AstronautRef(row["id"], row["display_name"]) if row else None

    def heart_rate_readings(self, astronaut_id: str) -> list[HeartRateReading]:
        """All numeric heart_rate readings in bpm, oldest first, any quality."""
        rows = self._conn.execute(
            "SELECT value, recorded_at, quality, source FROM readings"
            " WHERE astronaut_id = ? AND kind = 'heart_rate' AND unit = 'bpm'"
            " AND value IS NOT NULL ORDER BY recorded_at",
            (astronaut_id,),
        ).fetchall()
        return [
            HeartRateReading(
                value=row["value"],
                recorded_at=from_db_timestamp(row["recorded_at"]),
                quality=row["quality"],
                source=row["source"],
            )
            for row in rows
        ]
