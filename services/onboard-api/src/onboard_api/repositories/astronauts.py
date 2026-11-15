import sqlite3
from datetime import datetime

from onboard_api.repositories.database import from_db_timestamp, to_db_timestamp
from onboard_api.schemas.astronauts import Astronaut, AstronautCreate


def _to_astronaut(row: sqlite3.Row) -> Astronaut:
    return Astronaut(
        id=row["id"],
        display_name=row["display_name"],
        created_at=from_db_timestamp(row["created_at"]),
    )


class AstronautRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[Astronaut]:
        rows = self._conn.execute(
            "SELECT id, display_name, created_at FROM astronauts ORDER BY id"
        ).fetchall()
        return [_to_astronaut(row) for row in rows]

    def get(self, astronaut_id: str) -> Astronaut | None:
        row = self._conn.execute(
            "SELECT id, display_name, created_at FROM astronauts WHERE id = ?",
            (astronaut_id,),
        ).fetchone()
        return _to_astronaut(row) if row else None

    def exists(self, astronaut_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM astronauts WHERE id = ?", (astronaut_id,)
        ).fetchone()
        return row is not None

    def create(self, data: AstronautCreate, created_at: datetime) -> Astronaut | None:
        """Insert an astronaut. Returns None if the id already exists."""
        cursor = self._conn.execute(
            "INSERT INTO astronauts (id, display_name, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT (id) DO NOTHING",
            (data.id, data.display_name, to_db_timestamp(created_at)),
        )
        if cursor.rowcount == 0:
            return None
        return self.get(data.id)

    def rename(self, astronaut_id: str, display_name: str) -> Astronaut | None:
        """Change the display name. Returns None if the id does not exist."""
        cursor = self._conn.execute(
            "UPDATE astronauts SET display_name = ? WHERE id = ?", (display_name, astronaut_id)
        )
        if cursor.rowcount == 0:
            return None
        return self.get(astronaut_id)
