from datetime import datetime

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.readings import Reading, ReadingCreate
from onboard_api.schemas.sensors import SensorKind
from onboard_api.services.astronauts import ensure_astronaut_exists


class UnitMismatchError(Exception):
    def __init__(self, kind: str, unit: str, expected: str) -> None:
        super().__init__(
            f"Unit '{unit}' does not match the configured unit '{expected}' for '{kind}'"
        )


def record_reading(
    astronauts: AstronautRepository,
    sensors: SensorConfigRepository,
    readings: ReadingRepository,
    data: ReadingCreate,
    now: datetime,
) -> Reading:
    """Store a reading after checking the astronaut and the configured unit.

    A sensor whose configured unit is None accepts any unit.
    """
    ensure_astronaut_exists(astronauts, data.astronaut_id)
    config = sensors.get(data.kind)
    if config is None:
        # Every SensorKind is seeded with the schema; a missing row means the
        # database was modified outside the API.
        raise RuntimeError(f"sensor_config has no row for '{data.kind}'")
    if config.unit is not None and data.unit != config.unit:
        raise UnitMismatchError(data.kind, data.unit, config.unit)
    return readings.create(data, received_at=now)


def list_readings(
    astronauts: AstronautRepository,
    readings: ReadingRepository,
    astronaut_id: str,
    kind: SensorKind | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> list[Reading]:
    ensure_astronaut_exists(astronauts, astronaut_id)
    return readings.search(astronaut_id, kind=kind, since=since, until=until, limit=limit)
