"""Urgent medical incidents and their event history (also the ground telemetry queue).

Dedup: an `immediate` assistant response maps to a trigger key
`"<astronaut_id or ''>|<sorted rule ids>|<sorted event ids>"`. While an open incident
has that key, the same response reuses it (no new row, no new event); once it is
closed, the same key opens a new incident.

- Rule ids: `matched_rules[].rule_id`, plus `sos` when the response came from the SOS
  path. The SOS path is detected by the finding the medical workflow adds for it
  (`nodes._with_sos`): kind `event`, source `report`, detail `prompts.SOS_FINDING`.
  Card rules matched in the same turn stay in the key next to `sos`.
- Event ids: findings whose source is `event:<id>`.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from onboard_api.assistant.workflows.medical.prompts import SOS_FINDING
from onboard_api.repositories.database import from_db_timestamp, to_db_timestamp
from onboard_api.schemas.assistant import AssistantResponse, MatchedRule, Urgency
from onboard_api.schemas.incidents import (
    Acknowledgment,
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentStatus,
)

SOS_RULE_ID = "sos"


def trigger_key(response: AssistantResponse, astronaut_id: str | None) -> str:
    rule_ids = {rule.rule_id for rule in response.matched_rules}
    if any(
        f.kind == "event" and f.source == "report" and f.detail == SOS_FINDING
        for f in response.findings
    ):
        rule_ids.add(SOS_RULE_ID)
    event_ids = {f.source.removeprefix("event:") for f in response.findings if f.source.startswith("event:")}
    return f"{astronaut_id or ''}|{','.join(sorted(rule_ids))}|{','.join(sorted(event_ids))}"


@dataclass(frozen=True)
class QueuedIncidentEvent:
    """One undelivered event plus the incident summary the telemetry update needs."""

    id: str
    incident_id: str
    astronaut_id: str | None
    type: IncidentEventType
    occurred_at: datetime
    urgency: Urgency
    protocol_id: str | None
    protocol_version: str | None  # version of the primary protocol (protocol_id)
    matched_rules: list[MatchedRule]
    action: str | None
    acknowledged_by: str | None


def _dump(items: Iterable[BaseModel]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False)


def _ts(value: str | None) -> datetime | None:
    return from_db_timestamp(value) if value is not None else None


class IncidentRepository:
    def __init__(self, conn: sqlite3.Connection, telemetry_enabled: bool = True) -> None:
        self._conn = conn
        self._telemetry_enabled = telemetry_enabled

    def create_or_reuse(
        self,
        response: AssistantResponse,
        astronaut_id: str | None,
        reported_by: str | None,
        began_at: datetime,
    ) -> str:
        """Id of the open incident for this trigger, inserting it and its `created`
        event in one transaction when there is none."""
        key = trigger_key(response, astronaut_id)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT id FROM incidents WHERE trigger_key = ? AND status = 'open'", (key,)
            ).fetchone()
            if row:
                incident_id = row["id"]
            else:
                incident_id = str(uuid.uuid4())
                at = to_db_timestamp(began_at)
                self._conn.execute(
                    "INSERT INTO incidents (id, trigger_key, astronaut_id, reported_by, began_at,"
                    " urgency, action, protocol_id, steps_json, matched_rules_json, findings_json,"
                    " data_notices_json, mission_procedures_json, missing_guidance_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        incident_id, key, astronaut_id, reported_by, at,
                        response.urgency, response.action, response.protocol_id,
                        _dump(response.steps), _dump(response.matched_rules),
                        _dump(response.findings), json.dumps(response.data_notices, ensure_ascii=False),
                        _dump(response.mission_procedures),
                        json.dumps(response.missing_guidance, ensure_ascii=False),
                    ),
                )
                self._add_event(incident_id, "created", at)
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return incident_id

    def close(self, incident_id: str, at: datetime) -> bool:
        """Close an open incident and record its `closed` event. False if not open."""
        ts = to_db_timestamp(at)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._conn.execute(
                "UPDATE incidents SET status = 'closed', closed_at = ? WHERE id = ? AND status = 'open'",
                (ts, incident_id),
            )
            if cursor.rowcount:
                self._add_event(incident_id, "closed", ts)
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return cursor.rowcount == 1

    def acknowledge(self, incident_id: str, acknowledged_by: str, at: datetime) -> bool:
        """Record an `acknowledged` event. False when this person already acknowledged
        (the partial unique index makes the repeat a no-op)."""
        cursor = self._conn.execute(
            "INSERT INTO incident_events (id, incident_id, type, occurred_at, acknowledged_by)"
            " VALUES (?, ?, 'acknowledged', ?, ?) ON CONFLICT DO NOTHING",
            (str(uuid.uuid4()), incident_id, to_db_timestamp(at), acknowledged_by),
        )
        return cursor.rowcount == 1

    def _add_event(
        self, incident_id: str, type_: IncidentEventType, at: str, acknowledged_by: str | None = None
    ) -> None:
        self._conn.execute(
            "INSERT INTO incident_events (id, incident_id, type, occurred_at, acknowledged_by)"
            " VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), incident_id, type_, at, acknowledged_by),
        )

    def get(self, incident_id: str) -> Incident | None:
        row = self._conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return self._to_incident(row) if row else None

    def list_all(self, status: IncidentStatus | None = None) -> list[Incident]:
        """Open incidents first, then newest began_at first."""
        rows = self._conn.execute(
            "SELECT * FROM incidents WHERE ? IS NULL OR status = ?"
            " ORDER BY status = 'open' DESC, began_at DESC, rowid DESC",
            (status, status),
        ).fetchall()
        return [self._to_incident(row) for row in rows]

    def undelivered_events(self, limit: int) -> list[QueuedIncidentEvent]:
        """Events not yet accepted by ground, oldest first (occurred_at, then rowid)."""
        rows = self._conn.execute(
            "SELECT e.id, e.incident_id, e.type, e.occurred_at, e.acknowledged_by,"
            " i.astronaut_id, i.urgency, i.protocol_id, i.matched_rules_json, i.action"
            " FROM incident_events e JOIN incidents i ON i.id = e.incident_id"
            " WHERE e.delivered_at IS NULL ORDER BY e.occurred_at, e.rowid LIMIT ?",
            (limit,),
        ).fetchall()
        events = []
        for row in rows:
            rules = [MatchedRule.model_validate(r) for r in json.loads(row["matched_rules_json"])]
            version = next(
                (r.protocol_version for r in rules if r.protocol_id == row["protocol_id"]), None
            )
            events.append(
                QueuedIncidentEvent(
                    id=row["id"],
                    incident_id=row["incident_id"],
                    astronaut_id=row["astronaut_id"],
                    type=row["type"],
                    occurred_at=from_db_timestamp(row["occurred_at"]),
                    urgency=row["urgency"],
                    protocol_id=row["protocol_id"],
                    protocol_version=version,
                    matched_rules=rules,
                    action=row["action"],
                    acknowledged_by=row["acknowledged_by"],
                )
            )
        return events

    def mark_delivered(self, event_ids: list[str], at: datetime) -> None:
        """Set delivered_at on the given events that are still undelivered."""
        if not event_ids:
            return
        marks = ",".join("?" * len(event_ids))
        self._conn.execute(
            f"UPDATE incident_events SET delivered_at = ?"
            f" WHERE delivered_at IS NULL AND id IN ({marks})",
            (to_db_timestamp(at), *event_ids),
        )

    def _to_incident(self, row: sqlite3.Row) -> Incident:
        events = [
            IncidentEvent(
                id=e["id"],
                type=e["type"],
                occurred_at=from_db_timestamp(e["occurred_at"]),
                acknowledged_by=e["acknowledged_by"],
                delivered_at=_ts(e["delivered_at"]),
            )
            for e in self._conn.execute(
                "SELECT * FROM incident_events WHERE incident_id = ? ORDER BY occurred_at, rowid",
                (row["id"],),
            )
        ]
        if not self._telemetry_enabled:
            delivery = "disabled"
        elif any(e.delivered_at is None for e in events):
            delivery = "queued"
        else:
            delivery = "delivered"
        return Incident(
            id=row["id"],
            status=row["status"],
            astronaut_id=row["astronaut_id"],
            reported_by=row["reported_by"],
            began_at=from_db_timestamp(row["began_at"]),
            closed_at=_ts(row["closed_at"]),
            urgency=row["urgency"],
            action=row["action"],
            protocol_id=row["protocol_id"],
            steps=json.loads(row["steps_json"]),
            matched_rules=json.loads(row["matched_rules_json"]),
            findings=json.loads(row["findings_json"]),
            data_notices=json.loads(row["data_notices_json"]),
            mission_procedures=json.loads(row["mission_procedures_json"]),
            missing_guidance=json.loads(row["missing_guidance_json"]),
            acknowledgments=[
                Acknowledgment(acknowledged_by=e.acknowledged_by, acknowledged_at=e.occurred_at)
                for e in events
                if e.type == "acknowledged" and e.acknowledged_by
            ],
            events=events,
            ground_delivery=delivery,
        )
