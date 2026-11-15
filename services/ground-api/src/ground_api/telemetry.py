"""Receiver for contracts/telemetry v1 and the ground read API."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ground_api import storage
from ground_api.schemas import (
    Alert,
    BatchAccepted,
    CaseReportAck,
    CaseReportV1,
    CrewMember,
    Cursor,
    GroundCaseReport,
    GroundIncident,
    GroundReading,
    Link,
    SensorKind,
    TelemetryBatch,
    Urgency,
)
from ground_api.status import evaluate_sensor

Clock = Callable[[], datetime]


def get_clock() -> Clock:
    return lambda: datetime.now(UTC)


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    conn = storage.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


Connection = Annotated[sqlite3.Connection, Depends(get_connection)]
ClockDep = Annotated[Clock, Depends(get_clock)]

router = APIRouter()


@router.post("/telemetry/v1/batches", status_code=202)
def receive_batch(batch: TelemetryBatch, conn: Connection, clock: ClockDep) -> BatchAccepted:
    return storage.ingest(conn, batch, clock())


@router.get("/telemetry/v1/cursor")
def cursor(ship_id: str, conn: Connection) -> Cursor:
    return Cursor(last_reading_id=storage.last_reading_id(conn, ship_id))


@router.get("/link")
def link(conn: Connection, clock: ClockDep) -> Link:
    return storage.link(conn, clock())


@router.get("/crew")
def crew(conn: Connection, clock: ClockDep) -> list[CrewMember]:
    now = clock()
    sensors = storage.list_sensors(conn)
    return [
        CrewMember(
            astronaut_id=a.id,
            display_name=a.display_name,
            sensors=[
                evaluate_sensor(c, storage.latest_reading(conn, a.id, c.kind), now)
                for c in sensors
            ],
        )
        for a in storage.list_astronauts(conn)
    ]


@router.get("/astronauts/{astronaut_id}/readings")
def astronaut_readings(
    astronaut_id: str,
    conn: Connection,
    kind: SensorKind | None = None,
    since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[GroundReading]:
    if not storage.astronaut_exists(conn, astronaut_id):
        raise HTTPException(404, f"astronaut {astronaut_id} not found")
    if since is not None and since.tzinfo is None:
        raise HTTPException(422, "since must include a UTC offset")
    return storage.search_readings(conn, astronaut_id, kind, since, limit)


@router.get("/alerts")
def alerts(conn: Connection, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[Alert]:
    return storage.list_alerts(conn, limit)


@router.get("/incidents")
def incidents(conn: Connection) -> list[GroundIncident]:
    return storage.list_incidents(conn)


@router.get("/incidents/{incident_id}")
def incident(incident_id: str, conn: Connection) -> GroundIncident:
    found = storage.get_incident(conn, incident_id)
    if found is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    return found


@router.post("/case-reports/v1")
def receive_case_report(report: CaseReportV1, conn: Connection, clock: ClockDep) -> CaseReportAck:
    """contracts/case-report: 200 with the first receipt time, also for a resend."""
    return storage.insert_case_report(conn, report, clock())


@router.get("/case-reports")
def case_reports(
    conn: Connection,
    astronaut_id: str | None = None,
    incident_id: str | None = None,
    urgency: Urgency | None = None,
) -> list[GroundCaseReport]:
    return storage.list_case_reports(conn, astronaut_id, incident_id, urgency)


@router.get("/case-reports/{report_id}")
def case_report(report_id: str, conn: Connection) -> GroundCaseReport:
    found = storage.get_case_report(conn, report_id)
    if found is None:
        raise HTTPException(404, f"case report {report_id} not found")
    return found


@router.delete("/demo/incidents")
def reset_incidents(astronaut_id: str, request: Request, conn: Connection) -> dict[str, int]:
    """Demo reset: delete one astronaut's incidents, their updates and case reports (idempotent)."""
    if not request.app.state.settings.demo_controls_enabled:
        raise HTTPException(403, "demo controls are off (set GROUND_DEMO_CONTROLS_ENABLED=true)")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "DELETE FROM incident_updates WHERE (ship_id, incident_id) IN"
            " (SELECT ship_id, id FROM incidents WHERE astronaut_id = ?)",
            (astronaut_id,),
        )
        deleted = conn.execute("DELETE FROM incidents WHERE astronaut_id = ?", (astronaut_id,)).rowcount
        conn.execute("DELETE FROM case_reports WHERE astronaut_id = ?", (astronaut_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"deleted": deleted}
