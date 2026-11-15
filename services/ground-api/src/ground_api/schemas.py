"""Telemetry v1 models (mirror of contracts/telemetry/telemetry.v1.schema.json)
and the ground read API shapes."""

import uuid
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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
Quality = Literal["good", "suspect", "bad"]
ReadingStatus = Literal["normal", "alert", "no_data", "stale", "no_range"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Astronaut(Contract):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,31}$")
    display_name: str = Field(min_length=1, max_length=80)


class SensorConfig(Contract):
    kind: SensorKind
    unit: str | None
    stale_after_seconds: int | None = Field(gt=0)
    normal_min: float | None
    normal_max: float | None
    range_role: RangeRole
    provisional: bool
    range_source: str | None


class Reading(Contract):
    id: int = Field(ge=1)
    astronaut_id: str
    kind: SensorKind
    value: float | None
    value_text: str | None = Field(max_length=64)
    unit: str = Field(min_length=1, max_length=32)
    recorded_at: AwareDatetime
    received_at: AwareDatetime
    quality: Quality
    source: str = Field(min_length=1, max_length=64)


class TelemetryBatch(Contract):
    schema_version: Literal[1]
    ship_id: str = Field(min_length=1, max_length=64)
    batch_id: uuid.UUID
    sent_at: AwareDatetime
    astronauts: list[Astronaut]
    sensors: list[SensorConfig]
    readings: list[Reading] = Field(max_length=1000)


class BatchAccepted(BaseModel):
    accepted: int
    duplicates: int


class Cursor(BaseModel):
    last_reading_id: int | None


class GroundReading(Reading):
    ground_received_at: AwareDatetime


class SensorStatus(BaseModel):
    """Same precedence as onboard: no_data -> stale -> no_range -> alert/normal."""

    kind: SensorKind
    status: ReadingStatus
    latest: GroundReading | None
    age_seconds: int | None
    config: SensorConfig


class CrewMember(BaseModel):
    astronaut_id: str
    display_name: str
    sensors: list[SensorStatus]


class Link(BaseModel):
    ship_id: str | None
    last_batch_sent_at: AwareDatetime | None
    last_batch_received_at: AwareDatetime | None
    seconds_since_last_batch: int | None
    batches_received: int
    readings_received: int


class Alert(BaseModel):
    reading: GroundReading
    normal_min: float | None
    normal_max: float | None
    side: Literal["high", "low"]
