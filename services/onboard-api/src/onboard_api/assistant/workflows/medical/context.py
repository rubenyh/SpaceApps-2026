"""Readings and event sources for the medical workflow (injected; tests pass fakes)."""

from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from onboard_api.assistant.workflows.medical.state import ReadingsContext, VitalReading
from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.database import connect
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.assistant import OperationalEvent, SnapshotReading
from onboard_api.schemas.readings import is_simulated_source
from onboard_api.services.status import freshness

# Kinds read for every case. Pulse and SpO2 are always expected; the others
# are only described when present.
_EXPECTED = ("heart_rate", "spo2")
_OPTIONAL = (
    "muscle_density",
    "urine_ph",
    "urine_salinity",
    "urine_color",
    "urine_temperature",
    "urine_radiation_marker",
)
LABELS = {
    "heart_rate": "pulse",
    "spo2": "SpO₂",
    "muscle_density": "muscle sensor",
    "urine_ph": "urine pH",
    "urine_salinity": "urine salinity",
    "urine_color": "urine color",
    "urine_temperature": "urine sample temperature",
    "urine_radiation_marker": "urine radiation marker",
}
_QUALITY = {"suspect": "doubtful", "bad": "poor"}
_UNAVAILABLE = "Readings repository unavailable: no readings were checked."
# Validity when a kind has no sensor_config row (plan's provisional demo value).
# A row with stale_after_seconds NULL still means "never stale".
DEFAULT_STALE_AFTER_SECONDS = 300


def format_age(seconds: int) -> str:
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 7200:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h"


class SqliteReadingsProvider:
    """Latest readings per kind from the shared monitoring repository. Never raises."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    def load(self, astronaut_id: str | None, now: datetime) -> ReadingsContext:
        if not astronaut_id:
            return ReadingsContext(
                available=False,
                warnings=["No astronaut given: no readings were checked."],
            )
        # sqlite3.connect would create an empty file; a missing DB is "unavailable".
        if not self._db_path.is_file():
            return ReadingsContext(available=False, warnings=[_UNAVAILABLE])
        try:
            conn = connect(self._db_path)
            try:
                return self._load(conn, astronaut_id, now)
            finally:
                conn.close()
        except Exception:
            return ReadingsContext(available=False, warnings=[_UNAVAILABLE])

    def _load(self, conn, astronaut_id: str, now: datetime) -> ReadingsContext:
        if not AstronautRepository(conn).exists(astronaut_id):
            return ReadingsContext(
                available=False,
                warnings=[f"Astronaut '{astronaut_id}' not registered: no readings."],
            )
        readings = ReadingRepository(conn)
        configs = SensorConfigRepository(conn)
        ctx = ReadingsContext(available=True)

        def warn(kind: str, text: str) -> None:
            ctx.warnings.append(text)
            ctx.kind_warnings.setdefault(kind, []).append(text)

        for kind in _EXPECTED + _OPTIONAL:
            label = LABELS[kind]
            row = readings.latest(astronaut_id, kind)
            if row is None:
                if kind in _EXPECTED:
                    warn(kind, f"No {label} reading.")
                continue
            config = configs.get(kind)
            limit = config.stale_after_seconds if config else DEFAULT_STALE_AFTER_SECONDS
            fresh, age = freshness(row.recorded_at, now, limit)
            ctx.latest[kind] = VitalReading(
                kind=kind,
                value=row.value,
                value_text=row.value_text,
                unit=row.unit,
                recorded_at=row.recorded_at,
                quality=row.quality,
                source=row.source,
                age_seconds=age,
                stale=fresh != "current",
                id=row.id,
                received_at=row.received_at,
                freshness=fresh,
            )
            if fresh == "future":
                ahead = int((row.recorded_at - now).total_seconds())
                warn(
                    kind,
                    f"The {label} reading has a capture time in the future"
                    f" ({ahead} s ahead of the clock): not used as a current reading."
                )
            elif fresh == "stale":
                warn(
                    kind,
                    f"The {label} reading is {format_age(age)} old"
                    f" (valid for {limit} s): does not reflect the current state."
                )
            if row.quality in _QUALITY:
                warn(
                    kind,
                    f"The {label} reading has {_QUALITY[row.quality]} quality"
                    f" ({row.quality})."
                )
            if kind == "muscle_density":
                warn(
                    kind,
                    "Muscle sensor: method and unit pending; the value is not interpreted."
                )
        return ctx


def snapshot(ctx: ReadingsContext | None, kinds=None) -> list[SnapshotReading]:
    """Loaded readings as the contract's SnapshotReading (all, or only `kinds`)."""
    if ctx is None:
        return []
    return [
        SnapshotReading(
            id=r.id, kind=r.kind, value=r.value, value_text=r.value_text, unit=r.unit,
            recorded_at=r.recorded_at, received_at=r.received_at or r.recorded_at,
            quality=r.quality, source=r.source, simulated=is_simulated_source(r.source),
            freshness=r.freshness, age_seconds=r.age_seconds,
        )
        for k, r in ctx.latest.items()
        if kinds is None or k in kinds
    ]


class StaticEventSource:
    """Fixed list of ship events (demo fixture or tests)."""

    def __init__(self, events: list[OperationalEvent]) -> None:
        self._events = list(events)

    def active_events(self, now: datetime) -> list[OperationalEvent]:
        return [e for e in self._events if e.status == "active"]


def load_events_file(path: Path) -> list[OperationalEvent]:
    return TypeAdapter(list[OperationalEvent]).validate_json(Path(path).read_bytes())
