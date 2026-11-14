import sqlite3
from datetime import datetime
from typing import get_args

from onboard_api.repositories.database import to_db_timestamp
from onboard_api.schemas.sensors import SensorConfig, SensorConfigUpdate, SensorKind

_KIND_ORDER = {kind: index for index, kind in enumerate(get_args(SensorKind))}

_COLUMNS = (
    "kind, unit, stale_after_seconds, normal_min, normal_max,"
    " range_role, provisional, range_source"
)


def _to_config(row: sqlite3.Row) -> SensorConfig:
    return SensorConfig(
        kind=row["kind"],
        unit=row["unit"],
        stale_after_seconds=row["stale_after_seconds"],
        normal_min=row["normal_min"],
        normal_max=row["normal_max"],
        range_role=row["range_role"],
        provisional=bool(row["provisional"]),
        range_source=row["range_source"],
    )


class SensorConfigRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[SensorConfig]:
        """All configured sensors in SensorKind order."""
        rows = self._conn.execute(f"SELECT {_COLUMNS} FROM sensor_config").fetchall()
        rows = [row for row in rows if row["kind"] in _KIND_ORDER]
        rows.sort(key=lambda row: _KIND_ORDER[row["kind"]])
        return [_to_config(row) for row in rows]

    def get(self, kind: str) -> SensorConfig | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM sensor_config WHERE kind = ?", (kind,)
        ).fetchone()
        return _to_config(row) if row else None

    def update(
        self, kind: str, data: SensorConfigUpdate, updated_at: datetime
    ) -> SensorConfig | None:
        """Replace the editable fields of one sensor. Returns None for an unknown kind."""
        cursor = self._conn.execute(
            "UPDATE sensor_config SET unit = ?, stale_after_seconds = ?, normal_min = ?,"
            " normal_max = ?, range_role = ?, provisional = ?, range_source = ?,"
            " updated_at = ? WHERE kind = ?",
            (
                data.unit,
                data.stale_after_seconds,
                data.normal_min,
                data.normal_max,
                data.range_role,
                int(data.provisional),
                data.range_source,
                to_db_timestamp(updated_at),
                kind,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return self.get(kind)
