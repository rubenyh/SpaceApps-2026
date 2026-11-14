"""Storage of wellbeing inputs in wellbeing.db."""

import sqlite3
from datetime import date, datetime

from onboard_api.repositories.database import from_db_timestamp, to_db_timestamp
from onboard_api.wellbeing.schemas import (
    Checkin,
    CheckinUpsert,
    CoPresence,
    CoPresenceCreate,
    GroundPackage,
    GroundPackageCreate,
    GroundPackageStatus,
    Signal,
    SignalCreate,
    VisionSession,
    VisionSessionCreate,
    is_simulated_source,
)

_CHECKIN_FIELDS = (
    "sleep_hours",
    "sleep_quality",
    "energy",
    "mood",
    "interest",
    "stress",
    "crew_connection",
)


def _to_checkin(row: sqlite3.Row) -> Checkin:
    return Checkin(
        astronaut_id=row["astronaut_id"],
        day=date.fromisoformat(row["day"]),
        **{name: row[name] for name in _CHECKIN_FIELDS},
        comment=row["comment"],
        source=row["source"],
        submitted_at=from_db_timestamp(row["submitted_at"]),
        simulated=is_simulated_source(row["source"]),
    )


def _to_signal(row: sqlite3.Row) -> Signal:
    return Signal(
        id=row["id"],
        astronaut_id=row["astronaut_id"],
        kind=row["kind"],
        value=row["value"],
        unit=row["unit"],
        recorded_at=from_db_timestamp(row["recorded_at"]),
        received_at=from_db_timestamp(row["received_at"]),
        quality=row["quality"],
        source=row["source"],
        simulated=is_simulated_source(row["source"]),
    )


class WellbeingRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- check-ins ---

    def upsert_checkin(
        self, astronaut_id: str, day: date, data: CheckinUpsert, submitted_at: datetime
    ) -> Checkin:
        self._conn.execute(
            "INSERT INTO checkins (astronaut_id, day, sleep_hours, sleep_quality, energy,"
            " mood, interest, stress, crew_connection, comment, source, submitted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (astronaut_id, day) DO UPDATE SET"
            " sleep_hours = excluded.sleep_hours, sleep_quality = excluded.sleep_quality,"
            " energy = excluded.energy, mood = excluded.mood, interest = excluded.interest,"
            " stress = excluded.stress, crew_connection = excluded.crew_connection,"
            " comment = excluded.comment, source = excluded.source,"
            " submitted_at = excluded.submitted_at",
            (
                astronaut_id,
                day.isoformat(),
                *(getattr(data, name) for name in _CHECKIN_FIELDS),
                data.comment,
                data.source,
                to_db_timestamp(submitted_at),
            ),
        )
        row = self._conn.execute(
            "SELECT * FROM checkins WHERE astronaut_id = ? AND day = ?",
            (astronaut_id, day.isoformat()),
        ).fetchone()
        return _to_checkin(row)

    def list_checkins(
        self, astronaut_id: str, since: date | None = None, until: date | None = None
    ) -> list[Checkin]:
        """Newest first. since/until are inclusive."""
        clauses = ["astronaut_id = ?"]
        params: list[object] = [astronaut_id]
        if since is not None:
            clauses.append("day >= ?")
            params.append(since.isoformat())
        if until is not None:
            clauses.append("day <= ?")
            params.append(until.isoformat())
        rows = self._conn.execute(
            f"SELECT * FROM checkins WHERE {' AND '.join(clauses)} ORDER BY day DESC",
            params,
        ).fetchall()
        return [_to_checkin(row) for row in rows]

    # --- signals ---

    def create_signal(self, data: SignalCreate, received_at: datetime) -> Signal:
        cursor = self._conn.execute(
            "INSERT INTO signals (astronaut_id, kind, value, unit, recorded_at,"
            " received_at, quality, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.astronaut_id,
                data.kind,
                data.value,
                data.unit,
                to_db_timestamp(data.recorded_at),
                to_db_timestamp(received_at),
                data.quality,
                data.source,
            ),
        )
        row = self._conn.execute(
            "SELECT * FROM signals WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _to_signal(row)

    def list_signals(self, astronaut_id: str) -> list[Signal]:
        rows = self._conn.execute(
            "SELECT * FROM signals WHERE astronaut_id = ? ORDER BY recorded_at, id",
            (astronaut_id,),
        ).fetchall()
        return [_to_signal(row) for row in rows]

    # --- vision (stored as the validated JSON body) ---

    def create_vision_session(
        self, data: VisionSessionCreate, received_at: datetime
    ) -> VisionSession:
        cursor = self._conn.execute(
            "INSERT INTO vision_sessions (astronaut_id, started_at, body, received_at)"
            " VALUES (?, ?, ?, ?)",
            (
                data.astronaut_id,
                to_db_timestamp(data.started_at),
                data.model_dump_json(),
                to_db_timestamp(received_at),
            ),
        )
        return self._vision_rows("WHERE id = ?", (cursor.lastrowid,))[0]

    def list_vision_sessions(self, astronaut_id: str) -> list[VisionSession]:
        return self._vision_rows(
            "WHERE astronaut_id = ? ORDER BY started_at, id", (astronaut_id,)
        )

    def _vision_rows(self, where: str, params: tuple[object, ...]) -> list[VisionSession]:
        rows = self._conn.execute(
            f"SELECT id, body, received_at FROM vision_sessions {where}", params
        ).fetchall()
        result = []
        for row in rows:
            data = VisionSessionCreate.model_validate_json(row["body"])
            result.append(
                VisionSession(
                    **data.model_dump(),
                    id=row["id"],
                    received_at=from_db_timestamp(row["received_at"]),
                    simulated=is_simulated_source(data.source),
                )
            )
        return result

    # --- co-presence windows (JSON body + member index) ---

    def create_co_presence(self, data: CoPresenceCreate, received_at: datetime) -> CoPresence:
        self._conn.execute("BEGIN")
        try:
            cursor = self._conn.execute(
                "INSERT INTO co_presence (window_start, body, received_at) VALUES (?, ?, ?)",
                (
                    to_db_timestamp(data.window_start),
                    data.model_dump_json(),
                    to_db_timestamp(received_at),
                ),
            )
            window_id = cursor.lastrowid
            self._conn.executemany(
                "INSERT INTO co_presence_members (window_id, astronaut_id) VALUES (?, ?)",
                [(window_id, o.astronaut_id) for o in data.occupants],
            )
            self._conn.execute("COMMIT")
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        return self._co_presence_rows("WHERE c.id = ?", (window_id,))[0]

    def list_co_presence(self, astronaut_id: str) -> list[CoPresence]:
        return self._co_presence_rows(
            "JOIN co_presence_members m ON m.window_id = c.id"
            " WHERE m.astronaut_id = ? ORDER BY c.window_start, c.id",
            (astronaut_id,),
        )

    def _co_presence_rows(self, where: str, params: tuple[object, ...]) -> list[CoPresence]:
        rows = self._conn.execute(
            f"SELECT c.id, c.body, c.received_at FROM co_presence c {where}", params
        ).fetchall()
        result = []
        for row in rows:
            data = CoPresenceCreate.model_validate_json(row["body"])
            result.append(
                CoPresence(
                    **data.model_dump(),
                    id=row["id"],
                    received_at=from_db_timestamp(row["received_at"]),
                    simulated=is_simulated_source(data.source),
                )
            )
        return result

    # --- ground packages ---

    def create_ground_package(
        self, package_id: str, data: GroundPackageCreate, now: datetime
    ) -> GroundPackage:
        stamp = to_db_timestamp(now)
        self._conn.execute(
            "INSERT INTO ground_packages (id, astronaut_id, body, status,"
            " consent_recorded_at, created_at, updated_at)"
            " VALUES (?, ?, ?, 'queued', ?, ?, ?)",
            (package_id, data.astronaut_id, data.model_dump_json(), stamp, stamp, stamp),
        )
        package = self.get_ground_package(package_id)
        assert package is not None
        return package

    def get_ground_package(self, package_id: str) -> GroundPackage | None:
        rows = self._ground_rows("WHERE id = ?", (package_id,))
        return rows[0] if rows else None

    def list_ground_packages(self, astronaut_id: str) -> list[GroundPackage]:
        return self._ground_rows(
            "WHERE astronaut_id = ? ORDER BY created_at DESC, id", (astronaut_id,)
        )

    def set_ground_package_status(
        self, package_id: str, status: GroundPackageStatus, now: datetime
    ) -> None:
        self._conn.execute(
            "UPDATE ground_packages SET status = ?, updated_at = ? WHERE id = ?",
            (status, to_db_timestamp(now), package_id),
        )

    def _ground_rows(self, where: str, params: tuple[object, ...]) -> list[GroundPackage]:
        rows = self._conn.execute(
            "SELECT id, body, status, consent_recorded_at, created_at"
            f" FROM ground_packages {where}",
            params,
        ).fetchall()
        result = []
        for row in rows:
            data = GroundPackageCreate.model_validate_json(row["body"])
            result.append(
                GroundPackage(
                    **data.model_dump(exclude={"consent"}),
                    id=row["id"],
                    status=row["status"],
                    consent_statement_version=data.consent.statement_version,
                    consent_recorded_at=from_db_timestamp(row["consent_recorded_at"]),
                    created_at=from_db_timestamp(row["created_at"]),
                )
            )
        return result
