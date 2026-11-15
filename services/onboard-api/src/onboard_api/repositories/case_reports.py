"""Case report drafts and the ship to ground report queue (contracts/case-report).

draft -> queued (crew sends) -> received (ground acknowledged) or failed (ground
rejected it permanently). A failed report can be sent again.
"""

import json
import sqlite3
from datetime import datetime

from onboard_api.repositories.database import from_db_timestamp, to_db_timestamp
from onboard_api.schemas.assistant import AssistantResponse
from onboard_api.schemas.case_reports import CaseReportStatus, CaseReportV1


def _ts(value: str | None) -> datetime | None:
    return from_db_timestamp(value) if value is not None else None


class CaseReportRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_draft(
        self, response: AssistantResponse, astronaut_id: str | None, reported_by: str | None, at: datetime
    ) -> str:
        """Store response.report as a draft once per id; returns the stored status.
        Needs response.report.id; assessed_at falls back to `at`."""
        report = response.report
        version = report.knowledge_version
        self._conn.execute(
            "INSERT INTO case_reports (id, astronaut_id, reported_by, urgency, protocol_id, action,"
            " assessed_at, created_at, text, readings_json, knowledge_version_json, incident_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
            (
                report.id, astronaut_id, reported_by, response.urgency or "undetermined",
                response.protocol_id, response.action,
                # Required in the contract: without a snapshot time, use the draft time.
                to_db_timestamp(response.assessed_at or at),
                to_db_timestamp(at), report.text,
                json.dumps([r.model_dump(mode="json") for r in report.readings], ensure_ascii=False),
                version.model_dump_json() if version else None,
                response.incident.id if response.incident else None,
            ),
        )
        return self.status(report.id).status

    def status(self, report_id: str) -> CaseReportStatus | None:
        row = self._conn.execute("SELECT * FROM case_reports WHERE id = ?", (report_id,)).fetchone()
        if row is None:
            return None
        return CaseReportStatus(
            id=row["id"],
            status=row["status"],
            created_at=from_db_timestamp(row["created_at"]),
            queued_at=_ts(row["queued_at"]),
            received_at=_ts(row["received_at"]),
            error=row["error"],
        )

    def queue(self, report_id: str, sent_by: str | None, at: datetime) -> CaseReportStatus | None:
        """draft or failed -> queued. Queued or received reports stay as they are."""
        self._conn.execute(
            "UPDATE case_reports SET status = 'queued', sent_by = ?, queued_at = ?, error = NULL"
            " WHERE id = ? AND status IN ('draft', 'failed')",
            (sent_by, to_db_timestamp(at), report_id),
        )
        return self.status(report_id)

    def queued(self, ship_id: str, limit: int) -> list[CaseReportV1]:
        """Queued reports as ground payloads, oldest queued_at first."""
        rows = self._conn.execute(
            "SELECT * FROM case_reports WHERE status = 'queued' ORDER BY queued_at, rowid LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            CaseReportV1(
                report_id=row["id"],
                ship_id=ship_id,
                astronaut_id=row["astronaut_id"],
                reported_by=row["reported_by"],
                sent_by=row["sent_by"],
                urgency=row["urgency"],
                protocol_id=row["protocol_id"],
                action=row["action"],
                assessed_at=from_db_timestamp(row["assessed_at"]),
                created_at=from_db_timestamp(row["created_at"]),
                sent_at=from_db_timestamp(row["queued_at"]),
                incident_id=row["incident_id"],
                text=row["text"],
                readings=json.loads(row["readings_json"]),
                knowledge_version=json.loads(row["knowledge_version_json"] or "null"),
            )
            for row in rows
        ]

    def mark_received(self, report_id: str, received_at: datetime) -> None:
        self._conn.execute(
            "UPDATE case_reports SET status = 'received', received_at = ? WHERE id = ? AND status = 'queued'",
            (to_db_timestamp(received_at), report_id),
        )

    def mark_failed(self, report_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE case_reports SET status = 'failed', error = ? WHERE id = ? AND status = 'queued'",
            (error, report_id),
        )
