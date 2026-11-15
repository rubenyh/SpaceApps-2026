"""Telemetry v1 models (mirror of contracts/telemetry/telemetry.v1.schema.json)
and the ground read API shapes."""

import uuid
from typing import Annotated, Literal

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
Urgency = Literal["immediate", "review_required", "undetermined", "informational"]
IncidentUpdateType = Literal["created", "acknowledged", "closed"]
ReportedVia = Literal["console", "watch"]


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


class IncidentRule(Contract):
    rule_id: str
    protocol_id: str
    protocol_version: str


class IncidentUpdate(Contract):
    id: str = Field(min_length=1, max_length=64)
    incident_id: str = Field(min_length=1, max_length=64)
    astronaut_id: str | None
    type: IncidentUpdateType
    occurred_at: AwareDatetime
    urgency: Urgency
    protocol_id: str | None
    protocol_version: str | None
    matched_rules: list[IncidentRule]
    action: str | None
    acknowledged_by: str | None
    # Optional inside v1: old batches omit them.
    reported_via: ReportedVia | None = None
    reading_ids: list[Annotated[int, Field(ge=1)]] = []


class TelemetryBatch(Contract):
    schema_version: Literal[1]
    ship_id: str = Field(min_length=1, max_length=64)
    batch_id: uuid.UUID
    sent_at: AwareDatetime
    astronauts: list[Astronaut]
    sensors: list[SensorConfig]
    readings: list[Reading] = Field(max_length=1000)
    incident_updates: list[IncidentUpdate] = Field(default=[], max_length=500)


class BatchAccepted(BaseModel):
    accepted: int
    duplicates: int
    incident_updates_accepted: int = 0
    incident_updates_duplicates: int = 0


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


class GroundAcknowledgment(BaseModel):
    acknowledged_by: str
    acknowledged_at: AwareDatetime  # onboard occurred_at
    received_at: AwareDatetime


class GroundIncidentUpdate(BaseModel):
    id: str
    type: IncidentUpdateType
    occurred_at: AwareDatetime  # onboard clock
    received_at: AwareDatetime  # ground clock
    acknowledged_by: str | None


class GroundIncident(BaseModel):
    ship_id: str
    id: str
    astronaut_id: str | None
    began_at: AwareDatetime | None  # null until the created update arrives
    urgency: Urgency
    protocol_id: str | None
    protocol_version: str | None
    matched_rules: list[IncidentRule]
    action: str | None
    reported_via: ReportedVia | None
    readings: list[GroundReading]  # stored readings for reading_ids, in that order
    missing_reading_ids: int  # reading_ids not received by ground yet
    acknowledgments: list[GroundAcknowledgment]
    updates: list[GroundIncidentUpdate]  # occurred_at ascending
