"""Earth link state for the console, plus the demo controls of docs/demo-outage.md.

The pause is a controlled link outage: the publisher stops sending without counting
failures, so resume sends the queued backlog within a second (no retry backoff).
"""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from onboard_api.config import Settings
from onboard_api.dependencies import Connection, get_settings

router = APIRouter(tags=["telemetry"])


class EarthLink(BaseModel):
    enabled: bool  # telemetry publisher running
    paused: bool  # controlled outage (demo)
    failures: int  # failed sends in a row; > 0 means ground does not answer
    batches_sent: int


def require_demo_controls(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    if not settings.demo_controls_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "demo controls are off (set ONBOARD_DEMO_CONTROLS_ENABLED=true)"
        )


DEMO = [Depends(require_demo_controls)]


def _link(request: Request) -> EarthLink:
    pub = getattr(request.app.state, "telemetry_publisher", None)
    if pub is None:
        return EarthLink(enabled=False, paused=False, failures=0, batches_sent=0)
    return EarthLink(enabled=True, paused=pub.paused, failures=pub.failures, batches_sent=pub.batches_sent)


def _set_paused(request: Request, paused: bool) -> EarthLink:
    pub = getattr(request.app.state, "telemetry_publisher", None)
    if pub is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "telemetry is off (ONBOARD_TELEMETRY_ENABLED=false)")
    pub.paused = paused
    if not paused:
        pub.wake.set()  # skip any retry backoff still running
    return _link(request)


@router.get("/telemetry/link", response_model=EarthLink)
def get_link(request: Request) -> EarthLink:
    return _link(request)


@router.post("/telemetry/pause", response_model=EarthLink, dependencies=DEMO)
async def pause(request: Request) -> EarthLink:
    return _set_paused(request, True)


@router.post("/telemetry/resume", response_model=EarthLink, dependencies=DEMO)
async def resume(request: Request) -> EarthLink:
    return _set_paused(request, False)


@router.delete("/demo/incidents", dependencies=DEMO)
async def reset_incidents(astronaut_id: str, conn: Connection, request: Request) -> dict[str, int]:
    """Delete one astronaut's incidents, their queued events and case reports (idempotent).
    Readings stay: they are history, and ground already has them.

    Waits for a telemetry send in flight to finish first, so no batch with the
    deleted events reaches ground after this returns (the demo script then
    resets ground). The unsent batch is dropped and rebuilt from the DB.
    """
    pub = getattr(request.app.state, "telemetry_publisher", None)
    if pub is None:
        return {"deleted": _delete_incidents(conn, astronaut_id)}
    async with pub.sending:
        deleted = _delete_incidents(conn, astronaut_id)
        pub.pending = None
    return {"deleted": deleted}


def _delete_incidents(conn: sqlite3.Connection, astronaut_id: str) -> int:
    # ponytail: small SQLite delete on the event loop; fine for a demo-only route.
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "DELETE FROM incident_events WHERE incident_id IN (SELECT id FROM incidents WHERE astronaut_id = ?)",
            (astronaut_id,),
        )
        deleted = conn.execute("DELETE FROM incidents WHERE astronaut_id = ?", (astronaut_id,)).rowcount
        conn.execute("DELETE FROM case_reports WHERE astronaut_id = ?", (astronaut_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return deleted
