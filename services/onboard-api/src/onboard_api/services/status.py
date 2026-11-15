from datetime import datetime

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.assistant import Freshness
from onboard_api.schemas.readings import Reading
from onboard_api.schemas.sensors import SensorConfig
from onboard_api.schemas.status import AstronautStatus, ReadingStatus, SensorStatus
from onboard_api.services.astronauts import ensure_astronaut_exists

# Clock skew tolerated for capture times slightly ahead of the onboard clock.
FUTURE_SKEW_SECONDS = 5


def freshness(
    recorded_at: datetime, now: datetime, stale_after_seconds: int | None
) -> tuple[Freshness, int]:
    """One interpretation of a capture time against the onboard clock, shared by the
    live panel and the assistant. Returns (freshness, age in s, >= 0). A future
    reading stays visible with a clock warning and is never current evidence."""
    raw = int((now - recorded_at).total_seconds())
    if raw < -FUTURE_SKEW_SECONDS:
        return "future", 0
    age = max(0, raw)  # within the skew: not a "negative age"
    if stale_after_seconds is not None and age > stale_after_seconds:
        return "stale", age
    return "current", age


def evaluate_sensor(
    config: SensorConfig, latest: Reading | None, now: datetime
) -> SensorStatus:
    """Apply the status precedence documented on SensorStatus."""
    if latest is None:
        return SensorStatus(
            kind=config.kind, status="no_data", latest=None, age_seconds=None, config=config
        )

    fresh, age_seconds = freshness(latest.recorded_at, now, config.stale_after_seconds)

    status: ReadingStatus
    if fresh != "current":
        status = fresh
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
