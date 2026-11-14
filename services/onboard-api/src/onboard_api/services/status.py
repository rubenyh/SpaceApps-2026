from datetime import datetime

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.readings import Reading
from onboard_api.schemas.sensors import SensorConfig
from onboard_api.schemas.status import AstronautStatus, ReadingStatus, SensorStatus
from onboard_api.services.astronauts import ensure_astronaut_exists


def evaluate_sensor(
    config: SensorConfig, latest: Reading | None, now: datetime
) -> SensorStatus:
    """Apply the status precedence documented on SensorStatus."""
    if latest is None:
        return SensorStatus(
            kind=config.kind, status="no_data", latest=None, age_seconds=None, config=config
        )

    # Clamp to 0: a capture clock slightly ahead of ours is not "negative age".
    age_seconds = max(0, int((now - latest.recorded_at).total_seconds()))

    status: ReadingStatus
    if config.stale_after_seconds is not None and age_seconds > config.stale_after_seconds:
        status = "stale"
    elif (
        config.normal_min is None and config.normal_max is None
    ) or latest.value_text is not None:
        status = "no_range"
    elif latest.value is not None and (
        (config.normal_min is not None and latest.value < config.normal_min)
        or (config.normal_max is not None and latest.value > config.normal_max)
    ):
        status = "alert"
    else:
        status = "normal"

    return SensorStatus(
        kind=config.kind,
        status=status,
        latest=latest,
        age_seconds=age_seconds,
        config=config,
    )


def get_astronaut_status(
    astronauts: AstronautRepository,
    sensors: SensorConfigRepository,
    readings: ReadingRepository,
    astronaut_id: str,
    now: datetime,
) -> AstronautStatus:
    ensure_astronaut_exists(astronauts, astronaut_id)
    # list_all returns one config per SensorKind, in SensorKind order.
    sensor_statuses = [
        evaluate_sensor(config, readings.latest(astronaut_id, config.kind), now)
        for config in sensors.list_all()
    ]
    return AstronautStatus(
        astronaut_id=astronaut_id, generated_at=now, sensors=sensor_statuses
    )
