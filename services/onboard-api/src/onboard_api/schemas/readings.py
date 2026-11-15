from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from onboard_api.schemas.sensors import SensorKind

Quality = Literal["good", "suspect", "bad"]


class ReadingCreate(BaseModel):
    astronaut_id: str
    kind: SensorKind
    # Exactly one of value / value_text is set.
    value: float | None = None
    # Non-numeric readings. urine_color is sent as "#RRGGBB".
    value_text: str | None = Field(default=None, min_length=1, max_length=64)
    unit: str = Field(min_length=1, max_length=32)
    # Capture time. Must carry a UTC offset; stored and returned in UTC.
    recorded_at: AwareDatetime
    quality: Quality
    # Where the reading came from, e.g. "manual" or "serial:pulse".
    source: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _exactly_one_value(self) -> Self:
        if (self.value is None) == (self.value_text is None):
            raise ValueError("exactly one of value or value_text must be set")
        return self


class Reading(ReadingCreate):
    id: int
    received_at: AwareDatetime


def is_simulated_source(source: str) -> bool:
    """`simulated`, `demo` or `simulated:*` mark simulated data (db/data-dictionary.md)."""
    return source in ("simulated", "demo") or source.startswith("simulated:")
