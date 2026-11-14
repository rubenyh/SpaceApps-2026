from typing import Literal

from pydantic import AwareDatetime, BaseModel

from onboard_api.schemas.readings import Reading
from onboard_api.schemas.sensors import SensorConfig, SensorKind

ReadingStatus = Literal["normal", "alert", "no_data", "stale", "no_range"]


class SensorStatus(BaseModel):
    """Latest reading of one kind and how to present it.

    Status precedence:
      1. no reading at all                -> "no_data"
      2. older than stale_after_seconds   -> "stale" (value shown, not evaluated)
      3. no range, or a value_text value  -> "no_range"
      4. outside [normal_min, normal_max] -> "alert", otherwise "normal"
    """

    kind: SensorKind
    status: ReadingStatus
    latest: Reading | None
    age_seconds: int | None
    config: SensorConfig


class AstronautStatus(BaseModel):
    astronaut_id: str
    generated_at: AwareDatetime
    # Always one entry per SensorKind, in SensorKind order.
    sensors: list[SensorStatus]
