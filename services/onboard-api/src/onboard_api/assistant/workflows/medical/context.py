"""Readings and event sources for the medical workflow (injected; tests pass fakes)."""

from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from onboard_api.assistant.workflows.medical.state import ReadingsContext, VitalReading
from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.database import connect
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.assistant import OperationalEvent

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
    "heart_rate": "pulso",
    "spo2": "SpO₂",
    "muscle_density": "sensor muscular",
    "urine_ph": "pH de orina",
    "urine_salinity": "salinidad de orina",
    "urine_color": "color de orina",
    "urine_temperature": "temperatura de la muestra de orina",
    "urine_radiation_marker": "marcador de radiación en orina",
}
_QUALITY = {"suspect": "dudosa", "bad": "mala"}
_UNAVAILABLE = "Repositorio de lecturas no disponible: no se consultaron lecturas."


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
                warnings=["No se indicó el astronauta: no se consultaron lecturas."],
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
                warnings=[f"Astronauta '{astronaut_id}' no registrado: no hay lecturas."],
            )
        readings = ReadingRepository(conn)
        configs = SensorConfigRepository(conn)
        ctx = ReadingsContext(available=True)
        for kind in _EXPECTED + _OPTIONAL:
            label = LABELS[kind]
            row = readings.latest(astronaut_id, kind)
            if row is None:
                if kind in _EXPECTED:
                    ctx.warnings.append(f"Sin lectura de {label}.")
                continue
            config = configs.get(kind)
            limit = config.stale_after_seconds if config else None
            age = max(0, int((now - row.recorded_at).total_seconds()))
            stale = limit is not None and age > limit
            ctx.latest[kind] = VitalReading(
                kind=kind,
                value=row.value,
                value_text=row.value_text,
                unit=row.unit,
                recorded_at=row.recorded_at,
                quality=row.quality,
                source=row.source,
                age_seconds=age,
                stale=stale,
            )
            if stale:
                ctx.warnings.append(
                    f"La lectura de {label} tiene {format_age(age)} de antigüedad"
                    f" (vigencia {limit} s): no refleja el estado actual."
                )
            if row.quality in _QUALITY:
                ctx.warnings.append(
                    f"La lectura de {label} tiene calidad {_QUALITY[row.quality]}"
                    f" ({row.quality})."
                )
            if kind == "muscle_density":
                ctx.warnings.append(
                    "Sensor muscular: método y unidad pendientes; el valor no se interpreta."
                )
        return ctx


class StaticEventSource:
    """Fixed list of ship events (demo fixture or tests)."""

    def __init__(self, events: list[OperationalEvent]) -> None:
        self._events = list(events)

    def active_events(self, now: datetime) -> list[OperationalEvent]:
        return [e for e in self._events if e.status == "active"]


def load_events_file(path: Path) -> list[OperationalEvent]:
    return TypeAdapter(list[OperationalEvent]).validate_json(Path(path).read_bytes())
