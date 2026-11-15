"""Ship to ground telemetry publisher (contracts/telemetry/README.md, v1).

SQLite is the queue: the publisher sends readings with id > cursor, so a lost
link loses nothing and holds no memory. Incident updates are queued in
`incident_events` (`delivered_at IS NULL`) and marked delivered only after ground
answers 2xx for the batch carrying them. Queued case reports (contracts/case-report)
go after each confirmed batch, one POST each, until ground acknowledges the id.
It runs as one background task, reads
through the monitoring repositories and never raises into the app.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.case_reports import CaseReportRepository
from onboard_api.repositories.database import connect
from onboard_api.repositories.incidents import IncidentRepository, QueuedIncidentEvent
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.assistant import Urgency
from onboard_api.schemas.incidents import IncidentEventType
from onboard_api.schemas.readings import Reading
from onboard_api.schemas.sensors import SensorConfig

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
INCIDENT_BATCH_SIZE = 500
REPORT_BATCH_SIZE = 50
MAX_BACKOFF_SECONDS = 60.0
# While paused (demo link outage), how often run() checks for resume. No backoff.
PAUSE_CHECK_SECONDS = 0.5


class TelemetryAstronaut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str


class IncidentRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    protocol_id: str
    protocol_version: str


class IncidentUpdate(BaseModel):
    """One incident event. Only these fields: never message, reply or report text."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    incident_id: str = Field(min_length=1, max_length=64)
    astronaut_id: str | None
    type: IncidentEventType
    occurred_at: AwareDatetime
    urgency: Urgency
    protocol_id: str | None
    protocol_version: str | None
    matched_rules: list[IncidentRule]
    action: str | None
    acknowledged_by: str | None
    # Optional inside v1. reading_ids only on created; other types send [].
    reported_via: Literal["console", "watch"] | None = None
    reading_ids: list[Annotated[int, Field(ge=1)]] = []

    @classmethod
    def from_event(cls, e: QueuedIncidentEvent) -> "IncidentUpdate":
        return cls(
            id=e.id,
            incident_id=e.incident_id,
            astronaut_id=e.astronaut_id,
            type=e.type,
            occurred_at=e.occurred_at,
            urgency=e.urgency,
            protocol_id=e.protocol_id,
            protocol_version=e.protocol_version,
            matched_rules=[
                IncidentRule(rule_id=r.rule_id, protocol_id=r.protocol_id, protocol_version=r.protocol_version)
                for r in e.matched_rules
            ],
            action=e.action,
            acknowledged_by=e.acknowledged_by,
            reported_via=e.reported_via,
            reading_ids=e.reading_ids if e.type == "created" else [],
        )


class TelemetryBatch(BaseModel):
    """Mirror of contracts/telemetry/telemetry.v1.schema.json."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    ship_id: str = Field(min_length=1, max_length=64)
    batch_id: uuid.UUID
    sent_at: AwareDatetime
    astronauts: list[TelemetryAstronaut]
    sensors: list[SensorConfig]
    readings: list[Reading] = Field(max_length=1000)
    incident_updates: list[IncidentUpdate] = Field(default=[], max_length=INCIDENT_BATCH_SIZE)


class CaseReportAck(BaseModel):
    """Ground's answer to POST /case-reports/v1."""

    report_id: str
    received_at: AwareDatetime


class TelemetryPublisher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        db_path: Path,
        ship_id: str,
        interval_seconds: float,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._db_path = db_path
        self._ship_id = ship_id
        self._interval = interval_seconds
        self._clock = clock
        self.cursor: int | None = None
        self.cursor_known = False
        self.pending: TelemetryBatch | None = None
        self.failures = 0
        self.batches_sent = 0
        # Controlled link outage (POST /telemetry/pause): nothing is sent, nothing is lost.
        self.paused = False
        # Held for each send; the demo reset takes it so no send is in flight while it deletes.
        self.sending = asyncio.Lock()
        self.wake = asyncio.Event()  # set on resume to cut a backoff sleep short

    def _build_batch(self) -> TelemetryBatch:
        conn = connect(self._db_path)
        try:
            astronauts = AstronautRepository(conn).list_all()
            sensors = SensorConfigRepository(conn).list_all()
            readings = ReadingRepository(conn).after_id(self.cursor, BATCH_SIZE)
            events = IncidentRepository(conn).undelivered_events(INCIDENT_BATCH_SIZE)
        finally:
            conn.close()
        return TelemetryBatch(
            ship_id=self._ship_id,
            batch_id=uuid.uuid4(),
            sent_at=self._clock(),
            astronauts=[TelemetryAstronaut(id=a.id, display_name=a.display_name) for a in astronauts],
            sensors=sensors,
            readings=readings,
            incident_updates=[IncidentUpdate.from_event(e) for e in events],
        )

    def _mark_delivered(self, event_ids: list[str]) -> None:
        conn = connect(self._db_path)
        try:
            IncidentRepository(conn).mark_delivered(event_ids, self._clock())
        finally:
            conn.close()

    async def step(self) -> bool:
        """One attempt: fetch the cursor if unknown, then send one batch.
        Returns True if a full batch was sent (more may be waiting)."""
        if not self.cursor_known:
            response = await self._client.get(
                "/telemetry/v1/cursor", params={"ship_id": self._ship_id}
            )
            response.raise_for_status()
            self.cursor = response.json()["last_reading_id"]
            self.cursor_known = True
        if self.pending is None:
            # SQLite read off the event loop so a slow disk never stalls requests.
            self.pending = await asyncio.to_thread(self._build_batch)
        batch = self.pending  # local: a demo reset may drop self.pending meanwhile
        # Same batch_id on retry; sent_at stays the first attempt's time.
        response = await self._client.post(
            "/telemetry/v1/batches", json=batch.model_dump(mode="json")
        )
        response.raise_for_status()
        # Only after ground confirmed. If this fails the batch stays pending and is
        # resent; ground dedups it by batch_id.
        if batch.incident_updates:
            await asyncio.to_thread(
                self._mark_delivered, [u.id for u in batch.incident_updates]
            )
        if batch.readings:
            self.cursor = batch.readings[-1].id
        full = (
            len(batch.readings) >= BATCH_SIZE
            or len(batch.incident_updates) >= INCIDENT_BATCH_SIZE
        )
        self.pending = None
        self.batches_sent += 1
        return await self._send_case_reports() or full

    async def _send_case_reports(self) -> bool:
        """Send queued case reports oldest first (contracts/case-report). A network
        error, 5xx, 404/408/429 or a wrong ack raises: run() backs off and the report
        stays queued. Ground dedups by report id. True if a full batch was read."""
        reports = await asyncio.to_thread(self._with_reports, lambda r: r.queued(self._ship_id, REPORT_BATCH_SIZE))
        for report in reports:
            response = await self._client.post("/case-reports/v1", json=report.model_dump(mode="json"))
            code = response.status_code
            if 400 <= code < 500 and code not in (404, 408, 429):
                error = f"ground rejected (HTTP {code}): {response.text[:300]}"
                await asyncio.to_thread(self._with_reports, lambda r: r.mark_failed(report.report_id, error))
                continue
            response.raise_for_status()
            ack = CaseReportAck.model_validate(response.json())
            if ack.report_id != report.report_id:
                raise ValueError(f"ground acknowledged {ack.report_id!r} for case report {report.report_id!r}")
            await asyncio.to_thread(
                self._with_reports, lambda r: r.mark_received(report.report_id, ack.received_at)
            )
        return len(reports) >= REPORT_BATCH_SIZE

    def _with_reports(self, action: Callable[[CaseReportRepository], object]) -> object:
        conn = connect(self._db_path)
        try:
            return action(CaseReportRepository(conn))
        finally:
            conn.close()

    async def run(self) -> None:
        while True:
            if self.paused:
                await self._wait(PAUSE_CHECK_SECONDS)
                continue
            try:
                async with self.sending:
                    more = await self.step()
                self.failures = 0
                if more:
                    continue
                delay = self._interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # link down, ground error, DB busy: log and back off
                self.failures += 1
                delay = min(self._interval * 2 ** min(self.failures, 10), MAX_BACKOFF_SECONDS)
                logger.warning(
                    "telemetry send failed (%d in a row), retry in %.0fs: %r",
                    self.failures, delay, exc,
                )
            await self._wait(delay)

    async def _wait(self, delay: float) -> None:
        """Sleep `delay` seconds, or less when resume sets `wake`."""
        try:
            await asyncio.wait_for(self.wake.wait(), delay)
        except TimeoutError:
            pass
        self.wake.clear()  # after waiting, so a resume during a send is not lost
