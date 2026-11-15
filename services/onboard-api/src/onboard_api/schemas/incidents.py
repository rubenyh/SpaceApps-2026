"""Onboard incidents (db/migrations/onboard/0002_incidents.sql).

Mirrored by apps/spaceship-app/src/api/types.ts.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from onboard_api.schemas.assistant import (
    ActionStep,
    Finding,
    MatchedRule,
    MissionProcedure,
    Urgency,
)

IncidentStatus = Literal["open", "closed"]
IncidentEventType = Literal["created", "acknowledged", "closed"]
# disabled: telemetry off. queued: some event not yet accepted by ground. delivered: all accepted.
GroundDelivery = Literal["disabled", "queued", "delivered"]


class IncidentEvent(BaseModel):
    id: str
    type: IncidentEventType
    occurred_at: AwareDatetime  # onboard server clock
    acknowledged_by: str | None = None
    delivered_at: AwareDatetime | None = None


class Acknowledgment(BaseModel):
    acknowledged_by: str
    acknowledged_at: AwareDatetime


class AcknowledgmentCreate(BaseModel):
    acknowledged_by: str  # an existing astronaut id


class Incident(BaseModel):
    id: str
    status: IncidentStatus
    astronaut_id: str | None
    reported_by: str | None
    began_at: AwareDatetime  # onboard server clock
    closed_at: AwareDatetime | None
    urgency: Urgency
    action: str | None
    protocol_id: str | None
    steps: list[ActionStep]
    matched_rules: list[MatchedRule]
    findings: list[Finding]
    data_notices: list[str]
    mission_procedures: list[MissionProcedure]
    missing_guidance: list[str]
    acknowledgments: list[Acknowledgment]  # oldest first
    events: list[IncidentEvent]  # oldest first
    ground_delivery: GroundDelivery
