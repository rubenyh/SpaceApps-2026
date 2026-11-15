"""Case report delivery (contracts/case-report/README.md)."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from onboard_api.schemas.assistant import KnowledgeVersion, ReportTransmission, SnapshotReading, Urgency


class SendCaseReport(BaseModel):
    sent_by: str | None = None  # crew member who pressed send


class CaseReportStatus(BaseModel):
    id: str
    status: ReportTransmission
    created_at: AwareDatetime
    queued_at: AwareDatetime | None
    received_at: AwareDatetime | None  # ground's receipt time from its acknowledgement
    error: str | None  # why ground rejected it (status "failed")


class CaseReportV1(BaseModel):
    """Mirror of contracts/case-report/case-report.v1.schema.json."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    report_id: str
    ship_id: str = Field(min_length=1, max_length=64)
    astronaut_id: str | None
    reported_by: str | None
    sent_by: str | None
    urgency: Urgency
    protocol_id: str | None
    action: str | None
    assessed_at: AwareDatetime
    created_at: AwareDatetime
    sent_at: AwareDatetime
    incident_id: str | None
    text: str
    readings: list[SnapshotReading]
    knowledge_version: KnowledgeVersion | None
