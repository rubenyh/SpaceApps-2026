"""Ship to ground telemetry publisher (contracts/telemetry/README.md, v1).

SQLite is the queue: the publisher sends readings with id > cursor, so a lost
link loses nothing and holds no memory. It runs as one background task, reads
through the monitoring repositories and never raises into the app.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.database import connect
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.schemas.readings import Reading
from onboard_api.schemas.sensors import SensorConfig

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
MAX_BACKOFF_SECONDS = 60.0


class TelemetryAstronaut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str


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

    def _build_batch(self) -> TelemetryBatch:
        conn = connect(self._db_path)
        try:
            astronauts = AstronautRepository(conn).list_all()
            sensors = SensorConfigRepository(conn).list_all()
            readings = ReadingRepository(conn).after_id(self.cursor, BATCH_SIZE)
        finally:
            conn.close()
        return TelemetryBatch(
            ship_id=self._ship_id,
            batch_id=uuid.uuid4(),
            sent_at=self._clock(),
            astronauts=[TelemetryAstronaut(id=a.id, display_name=a.display_name) for a in astronauts],
            sensors=sensors,
            readings=readings,
        )

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
        # Same batch_id on retry; sent_at stays the first attempt's time.
        response = await self._client.post(
            "/telemetry/v1/batches", json=self.pending.model_dump(mode="json")
        )
        response.raise_for_status()
        if self.pending.readings:
            self.cursor = self.pending.readings[-1].id
        full = len(self.pending.readings) >= BATCH_SIZE
        self.pending = None
        self.batches_sent += 1
        return full

    async def run(self) -> None:
        while True:
            try:
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
            await asyncio.sleep(delay)
