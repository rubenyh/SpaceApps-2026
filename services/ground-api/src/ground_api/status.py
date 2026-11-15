"""Status rules copied from onboard-api services/status.py (separate uv projects).
Keep both in sync."""

from datetime import datetime
from typing import Literal

from ground_api.schemas import GroundReading, Reading, ReadingStatus, SensorConfig, SensorStatus


def evaluate_sensor(
    config: SensorConfig, latest: GroundReading | None, now: datetime
) -> SensorStatus:
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
        kind=config.kind, status=status, latest=latest, age_seconds=age_seconds, config=config
    )


def alert_side(config: SensorConfig | None, reading: Reading) -> Literal["high", "low"] | None:
    """Side of the health range a reading falls outside, at ingest. Sample-validity
    ranges and urine_radiation_marker never alert."""
    if (
        config is None
        or config.range_role != "health"
        or config.kind == "urine_radiation_marker"
        or reading.value is None
        or reading.value_text is not None
    ):
        return None
    if config.normal_max is not None and reading.value > config.normal_max:
        return "high"
    if config.normal_min is not None and reading.value < config.normal_min:
        return "low"
    return None
