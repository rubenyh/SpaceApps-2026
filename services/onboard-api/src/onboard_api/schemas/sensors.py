from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

SensorKind = Literal[
    "heart_rate",
    "spo2",
    "muscle_density",
    "urine_ph",
    "urine_salinity",
    "urine_color",
    "urine_temperature",
    "urine_radiation_marker",
]
RangeRole = Literal["health", "sample_validity"]


class SensorConfigUpdate(BaseModel):
    """Full replacement of the editable fields of one sensor's configuration."""

    # None: the unit is not defined yet, readings may carry any unit.
    unit: str | None
    # None: readings of this kind never become "stale".
    stale_after_seconds: int | None = Field(gt=0)
    # Both None: no reference range, status is "no_range".
    normal_min: float | None
    normal_max: float | None
    # "sample_validity": the range says whether the sample is usable, not
    # whether the astronaut is healthy (urine temperature).
    range_role: RangeRole
    provisional: bool
    range_source: str | None

    @model_validator(mode="after")
    def _min_not_above_max(self) -> Self:
        if (
            self.normal_min is not None
            and self.normal_max is not None
            and self.normal_min > self.normal_max
        ):
            raise ValueError("normal_min must not be greater than normal_max")
        return self


class SensorConfig(SensorConfigUpdate):
    kind: SensorKind
