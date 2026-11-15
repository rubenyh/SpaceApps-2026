"""Urgent incidents (#43): one row per trigger, survives restarts, never hides the action."""

import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from assistant.fakes import FailingLLM, FailingRetriever, Forbidden
from assistant.medical_cases import _event
from assistant.test_post_cases import post
from conftest import T0
from onboard_api.dependencies import get_incident_recorder
from onboard_api.repositories.database import connect
from onboard_api.repositories.incidents import IncidentRepository

OFFLINE = {"llm": Forbidden("llm"), "retriever": Forbidden("retriever")}


def ask(client, db_path, message, astronaut_id="ana", **kw):
    request = {"astronaut_id": astronaut_id, "message": message, "reported_by": "ben"}
    return post(client, db_path, request, **{**OFFLINE, **kw})[0]


def count(db_path, table="incidents") -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def crew(client: TestClient, astronaut: str) -> TestClient:
    assert client.post("/astronauts", json={"id": "ben", "display_name": "Ben"}).status_code == 201
    return client


@pytest.mark.parametrize("message", ["SOS", "I can't breathe"], ids=["sos", "card"])
def test_immediate_creates_one_incident_with_all_fields(crew, db_path, message) -> None:
    body = ask(crew, db_path, message)
    assert body["urgency"] == "immediate"
    ref = body["incident"]
    assert ref["recorded"] is True and ref["error"] is None and ref["id"]
    assert count(db_path) == 1 and count(db_path, "incident_events") == 1

    incident = crew.get(f"/incidents/{ref['id']}").json()
    assert incident["status"] == "open" and incident["closed_at"] is None
    assert incident["astronaut_id"] == "ana" and incident["reported_by"] == "ben"
    assert incident["began_at"] == "2026-11-14T12:00:00Z"
    for key in ("urgency", "action", "protocol_id", "steps", "matched_rules", "findings",
                "data_notices", "mission_procedures", "missing_guidance"):
        assert incident[key] == body[key], key
    assert incident["acknowledgments"] == []
    [event] = incident["events"]
    assert event["type"] == "created" and event["occurred_at"] == incident["began_at"]
    assert event["delivered_at"] is None
    assert incident["ground_delivery"] == "disabled"  # conftest clients run with telemetry off


def test_non_urgent_answer_has_no_incident(crew, db_path) -> None:
    body = ask(crew, db_path, "shortness of breath", llm=FailingLLM(), retriever=FailingRetriever())
    assert body["urgency"] != "immediate" and body["incident"] is None
    assert count(db_path) == 0


def test_repeat_reuses_the_open_incident(crew, db_path) -> None:
    first = ask(crew, db_path, "I can't breathe")["incident"]["id"]
    assert ask(crew, db_path, "I can't breathe")["incident"]["id"] == first
    assert count(db_path) == 1 and count(db_path, "incident_events") == 1


def test_other_astronaut_rules_or_event_open_a_new_incident(crew, db_path) -> None:
    ids = {
        ask(crew, db_path, "I can't breathe")["incident"]["id"],
        ask(crew, db_path, "I can't breathe", astronaut_id="ben")["incident"]["id"],
        ask(crew, db_path, "SOS")["incident"]["id"],  # rule `sos` instead of the card rule
    }
    rad = _event("radiation", origin="dosimeter:area-2")
    for event_id in ("evt-rad-1", "evt-rad-1", "evt-rad-2"):
        body = ask(crew, db_path, "Tengo náuseas", events=[{**rad, "id": event_id}])
        assert body["urgency"] == "immediate"
        ids.add(body["incident"]["id"])
    assert len(ids) == count(db_path) == 5


def test_closed_incident_is_not_reused(crew, db_path) -> None:
    first = ask(crew, db_path, "SOS")["incident"]["id"]
    conn = connect(db_path)
    assert IncidentRepository(conn).close(first, T0 + timedelta(minutes=5))
    conn.close()
    second = ask(crew, db_path, "SOS")["incident"]["id"]
    assert second != first and count(db_path) == 2
    listed = crew.get("/incidents").json()
    assert [i["id"] for i in listed] == [second, first]  # open first
    assert [i["id"] for i in crew.get("/incidents?status=closed").json()] == [first]
    closed = crew.get(f"/incidents/{first}").json()
    assert closed["closed_at"] == "2026-11-14T12:05:00Z"
    assert [e["type"] for e in closed["events"]] == ["created", "closed"]


def test_incident_survives_restart(make_client, db_path) -> None:
    client = make_client()
    assert client.post("/astronauts", json={"id": "ana", "display_name": "Ana"}).status_code == 201
    body = ask(client, db_path, "SOS")
    restarted = make_client()
    response = restarted.get(f"/incidents/{body['incident']['id']}")
    assert response.status_code == 200 and response.json()["action"] == body["action"]
    assert restarted.get("/incidents/missing").status_code == 404


def test_insert_failure_keeps_the_action(crew, db_path) -> None:
    expected = ask(crew, db_path, "I can't breathe", astronaut_id="ben")

    def failing(*_args):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    crew.app.dependency_overrides[get_incident_recorder] = lambda: failing
    body = ask(crew, db_path, "I can't breathe", astronaut_id="ben")
    assert body["action"] == expected["action"] and body["steps"] == expected["steps"]
    assert body["incident"]["recorded"] is False and body["incident"]["id"] is None
    assert "readonly" in body["incident"]["error"]


def test_urgent_path_with_ollama_down_and_telemetry_off(crew, db_path) -> None:
    assert crew.app.state.settings.telemetry_enabled is False
    body = ask(crew, db_path, "I can't breathe", llm=FailingLLM(), retriever=FailingRetriever())
    assert body["urgency"] == "immediate" and body["action"] and body["steps"]
    assert body["incident"]["recorded"] is True
    assert count(db_path) == 1


def test_telemetry_queue_and_ground_delivery(crew, db_path) -> None:
    body = ask(crew, db_path, "I can't breathe")
    conn = connect(db_path)
    repo = IncidentRepository(conn, telemetry_enabled=True)
    [queued] = repo.undelivered_events(500)
    assert queued.incident_id == body["incident"]["id"] and queued.type == "created"
    assert queued.astronaut_id == "ana" and queued.occurred_at == T0
    assert queued.urgency == "immediate" and queued.action == body["action"]
    assert queued.protocol_id == body["protocol_id"]
    assert queued.protocol_version == body["matched_rules"][0]["protocol_version"]
    assert [r.rule_id for r in queued.matched_rules] == [r["rule_id"] for r in body["matched_rules"]]
    assert repo.get(queued.incident_id).ground_delivery == "queued"

    repo.mark_delivered([queued.id], T0 + timedelta(seconds=5))
    repo.mark_delivered([queued.id], T0 + timedelta(seconds=9))  # already delivered: unchanged
    assert repo.undelivered_events(500) == []
    incident = repo.get(queued.incident_id)
    assert incident.ground_delivery == "delivered"
    assert incident.events[0].delivered_at == T0 + timedelta(seconds=5)
    conn.close()


def test_acknowledgment_is_stored_idempotent_and_separate_from_ground(crew, db_path, clock) -> None:
    assert crew.app.state.settings.telemetry_enabled is False  # ground unreachable / off
    incident_id = ask(crew, db_path, "I can't breathe")["incident"]["id"]
    url = f"/incidents/{incident_id}/acknowledgments"

    clock.now = T0 + timedelta(minutes=1)
    first = crew.post(url, json={"acknowledged_by": "ben"})
    assert first.status_code == 201
    body = first.json()
    assert body["acknowledgments"] == [
        {"acknowledged_by": "ben", "acknowledged_at": "2026-11-14T12:01:00Z"}
    ]
    ack = body["events"][-1]
    assert ack["type"] == "acknowledged" and ack["acknowledged_by"] == "ben"
    assert ack["occurred_at"] == "2026-11-14T12:01:00Z" and ack["delivered_at"] is None
    assert body["ground_delivery"] == "disabled"

    clock.now = T0 + timedelta(minutes=2)
    repeat = crew.post(url, json={"acknowledged_by": "ben"})
    assert repeat.status_code == 200 and repeat.json() == body
    assert count(db_path, "incident_events") == 2

    other = crew.post(url, json={"acknowledged_by": "ana"})
    assert other.status_code == 201
    assert [a["acknowledged_by"] for a in other.json()["acknowledgments"]] == ["ben", "ana"]
    assert count(db_path, "incident_events") == 3
    assert crew.get(f"/incidents/{incident_id}").json() == other.json()  # same state on reload


def test_acknowledgment_errors(crew, db_path) -> None:
    incident_id = ask(crew, db_path, "SOS")["incident"]["id"]
    missing = crew.post("/incidents/missing/acknowledgments", json={"acknowledged_by": "ben"})
    assert missing.status_code == 404
    unknown = crew.post(f"/incidents/{incident_id}/acknowledgments", json={"acknowledged_by": "zoe"})
    assert unknown.status_code == 422
    assert count(db_path, "incident_events") == 1
