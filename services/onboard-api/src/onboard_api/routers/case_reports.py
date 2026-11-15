"""Case report drafts and crew send (contracts/case-report/README.md). The telemetry
publisher delivers queued reports to ground."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from onboard_api.config import Settings
from onboard_api.dependencies import ClockDep, Connection, get_settings
from onboard_api.repositories.case_reports import CaseReportRepository
from onboard_api.repositories.database import connect
from onboard_api.schemas.assistant import AssistantResponse
from onboard_api.schemas.case_reports import CaseReportStatus, SendCaseReport

router = APIRouter(prefix="/case-reports", tags=["case-reports"])

# (response, astronaut_id, reported_by, created_at) -> stored transmission status.
DraftStore = Callable[[AssistantResponse, str | None, str | None, datetime], str]


def get_draft_store(settings: Annotated[Settings, Depends(get_settings)]) -> DraftStore:
    """Opens its connection only when called, so a broken database cannot fail the
    assistant request (the caller keeps the reply)."""

    def store(response: AssistantResponse, astronaut_id: str | None, reported_by: str | None, at: datetime) -> str:
        conn = connect(settings.db_path)
        try:
            return CaseReportRepository(conn).save_draft(response, astronaut_id, reported_by, at)
        finally:
            conn.close()

    return store


DraftStoreDep = Annotated[DraftStore, Depends(get_draft_store)]


def _found(report: CaseReportStatus | None, report_id: str) -> CaseReportStatus:
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"case report {report_id} not found")
    return report


@router.post("/{report_id}/send", response_model=CaseReportStatus)
async def send(
    report_id: str, body: SendCaseReport, conn: Connection, clock: ClockDep, request: Request
) -> CaseReportStatus:
    # async so wake.set() runs on the event loop (asyncio.Event is not thread-safe).
    # ponytail: one small SQLite update on the loop, like the demo reset.
    report = _found(CaseReportRepository(conn).queue(report_id, body.sent_by, clock()), report_id)
    pub = getattr(request.app.state, "telemetry_publisher", None)
    if pub is not None and report.status == "queued":
        pub.wake.set()  # send now instead of at the next interval
    return report


@router.get("/{report_id}", response_model=CaseReportStatus)
def get(report_id: str, conn: Connection) -> CaseReportStatus:
    return _found(CaseReportRepository(conn).status(report_id), report_id)
