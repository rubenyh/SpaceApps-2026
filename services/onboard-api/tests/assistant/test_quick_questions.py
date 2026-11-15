"""Issue #85: readings judged at load time (not request start) and the deterministic
status quick questions. HTTP endpoint, real SQLite, no Ollama or ChromaDB."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from assistant.fakes import FakeEvents, Forbidden
from conftest import T0, FakeClock, reading_payload
from onboard_api.assistant.integrations import DependencyUnavailable
from onboard_api.assistant.state import AssistantDeps
from onboard_api.assistant.status import status_question
from onboard_api.assistant.workflows.medical.context import SqliteReadingsProvider
from onboard_api.dependencies import get_assistant_deps
from onboard_api.repositories.database import connect
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.schemas.readings import ReadingCreate

SIM = "simulated:pulse-ox"


class CaptureDuringInterpretation:
    """Interpreter that is slow: the simulator stores a pulse sample 11 s after the
    request started, and readings load at T+12 s. Then reports itself down."""

    def __init__(self, db_path, clock: FakeClock, source: str = SIM) -> None:
        self.db_path, self.clock, self.source = db_path, clock, source

    def chat_json(self, system, user, schema):
        conn = connect(self.db_path)
        try:
            ReadingRepository(conn).create(
                ReadingCreate(astronaut_id="ana", kind="heart_rate", value=88, unit="bpm",
                              recorded_at=T0 + timedelta(seconds=11), quality="good",
                              source=self.source),
                received_at=T0 + timedelta(seconds=11),
            )
            conn.commit()
        finally:
            conn.close()
        self.clock.now = T0 + timedelta(seconds=12)
        raise DependencyUnavailable("interpreter down")

    def chat(self, system, user):
        raise DependencyUnavailable("ollama down")


def _deps(client: TestClient, db_path, llm=None) -> tuple[Forbidden, Forbidden]:
    llm = llm or Forbidden("llm")
    retriever = Forbidden("retriever")
    client.app.dependency_overrides[get_assistant_deps] = lambda: AssistantDeps(
        llm=llm, retriever=retriever, readings=SqliteReadingsProvider(db_path),
        events=FakeEvents(),
    )
    return llm, retriever


def _ask(client: TestClient, message: str, **extra) -> dict:
    response = client.post("/assistant/messages", json={"message": message, "astronaut_id": "ana", **extra})
    assert response.status_code == 200, response.text
    return response.json()


def _snap(body: dict) -> dict[str, dict]:
    return {r["kind"]: r for r in body["readings_snapshot"]}


def test_sample_captured_during_interpretation_is_current_and_simulated(
    client: TestClient, astronaut: str, clock: FakeClock, db_path
) -> None:
    _deps(client, db_path, CaptureDuringInterpretation(db_path, clock))
    body = _ask(client, "im dizzy")
    assert body["assessed_at"] == "2026-11-14T12:00:12Z"
    pulse = _snap(body)["heart_rate"]
    assert pulse["freshness"] == "current" and pulse["simulated"] is True
    assert pulse["recorded_at"] == "2026-11-14T12:00:11Z" and pulse["age_seconds"] == 1
    assert not any("future" in n for n in body["data_notices"])
    assert body["assessment"] == {
        "urgency": "review_required",
        "urgency_label": "Review required",
        "reported": "Dizziness reported",
        "action": "Limit movement and monitor",
        "escalation": [
            "If weakness on one side, impaired speech or loss of vision appears, treat it as an emergency."
        ],
    }
    report = body["report"]
    assert report["transmission"] == "draft" and report["id"]
    assert [r["kind"] for r in report["readings"]] == ["heart_rate"]
    assert "Generated: 2026-11-14T12:00:12Z" in report["text"]
    assert "not_sent" not in report["text"]
    causes = {c["id"]: c for c in body["possible_causes"]}
    assert causes["space_motion_sickness"]["status"] == "insufficient_evidence"


def test_hardware_sample_is_not_simulated(
    client: TestClient, astronaut: str, clock: FakeClock, db_path
) -> None:
    _deps(client, db_path, CaptureDuringInterpretation(db_path, clock, source="serial:pulse"))
    pulse = _snap(_ask(client, "im dizzy"))["heart_rate"]
    assert pulse["simulated"] is False and pulse["freshness"] == "current"


def test_sample_ahead_of_clock_at_load_is_future_and_excluded(
    client: TestClient, astronaut: str, db_path
) -> None:
    _deps(client, db_path)
    client.post("/readings", json=reading_payload(value=88, recorded_at="2026-11-14T12:01:00Z", source=SIM))
    body = _ask(client, "im dizzy")
    assert _snap(body)["heart_rate"]["freshness"] == "future"
    assert any("capture time in the future" in n for n in body["data_notices"])
    pulse_finding = next(f for f in body["findings"] if f["source"] == "sqlite:heart_rate")
    assert "stale" in pulse_finding["evidence_flags"]  # never current evidence
    # The live panel shares the interpretation.
    status = {s["kind"]: s for s in client.get("/astronauts/ana/status").json()["sensors"]}
    assert status["heart_rate"]["status"] == "future"


def test_crew_member_with_no_readings(client: TestClient, astronaut: str, db_path) -> None:
    _deps(client, db_path)
    summary = _ask(client, "Summarize my status today")
    assert summary["workflow"] == "status" and summary["readings_snapshot"] == []
    assert "No readings recorded for ana." in summary["reply"]
    missing = _ask(client, "Which readings am I missing?")
    assert "Never measured: pulse, SpO₂, muscle sensor" in missing["reply"]


def test_unknown_crew_member_is_unavailable(client: TestClient, astronaut: str, db_path) -> None:
    _deps(client, db_path)
    body = client.post("/assistant/messages", json={"message": "missing readings", "astronaut_id": "zoe"}).json()
    assert body["workflow"] == "status"
    assert body["reply"].startswith("Readings unavailable:") and "zoe" in body["reply"]


def test_both_quick_questions_offline(
    client: TestClient, astronaut: str, clock: FakeClock, db_path
) -> None:
    llm, retriever = _deps(client, db_path)
    clock.now = T0 + timedelta(minutes=30)
    posts = [
        reading_payload(value=72, recorded_at="2026-11-14T12:29:00Z", source=SIM),  # fresh simulated
        reading_payload(kind="spo2", value=97, unit="%", recorded_at="2026-11-14T12:00:00Z"),  # stale
        reading_payload(kind="urine_ph", value=6.0, unit="pH", recorded_at="2026-11-13T09:00:00Z"),
        reading_payload(kind="urine_salinity", value=1.2, unit="g/L", recorded_at="2026-11-14T12:29:00Z",
                        quality="bad"),
        reading_payload(kind="muscle_density", value=1.1, unit="a.u.", recorded_at="2026-11-14T12:29:00Z"),
        reading_payload(kind="urine_color", value=None, value_text="#E0C060", unit="rgb_hex",
                        recorded_at="2026-11-14T12:40:00Z"),  # future-dated
    ]
    for p in posts:
        assert client.post("/readings", json=p).status_code == 201

    summary = _ask(client, "Summarize my status today")
    assert summary["workflow"] == "status" and summary["needs_clarification"] is False
    reply = summary["reply"]
    assert reply.startswith("Status for ana on 2026-11-14, as of 12:30 UTC.")
    assert "- Pulse: 72 bpm (12:29 UTC) · Simulated · simulated:pulse-ox." in reply
    assert "- Urine pH: Last known 6 pH (2026-11-13 09:00 UTC)" in reply
    assert summary["assessed_at"] == "2026-11-14T12:30:00Z"

    missing = _ask(client, "Which readings am I missing?")["reply"]
    assert "- Never measured: urine sample temperature, urine radiation marker." in missing
    assert "- Stale: SpO₂ (30 min old), urine pH (27 h old)." in missing
    assert "- Future-dated (clock warning, not used): urine color (600 s ahead)." in missing
    assert "- Poor quality: urine salinity (bad)." in missing
    assert "- Available: pulse (simulated), muscle sensor." in missing
    assert llm.calls == [] and retriever.calls == []


def test_status_question_keeps_pending_follow_up(client: TestClient, astronaut: str, db_path) -> None:
    _deps(client, db_path)
    pending = {"question_id": "symptom", "question": "What do you feel?", "astronaut_id": "ana",
               "observations": []}
    body = _ask(client, "Which readings am I missing?", clarification=pending)
    assert body["workflow"] == "status" and body["needs_clarification"] is False
    assert body["clarification"] == pending


def test_sos_still_goes_to_medical(client: TestClient, astronaut: str, db_path) -> None:
    _deps(client, db_path)
    assert _ask(client, "SOS which readings am I missing")["workflow"] == "medical"


@pytest.mark.parametrize("text, kind", [
    ("summarize my status today", "summary"),
    ("sumarize my status", "summary"),
    ("summarise my status today!", "summary"),
    ("my status today?", "summary"),
    ("which readings am i missing?", "missing"),
    ("what readings am i missing", "missing"),
    ("missing readings", "missing"),
    ("which readings am i mising", "missing"),
    ("i feel dizzy", None),
    ("what is a normal pulse?", None),
])
def test_status_question_variants(text: str, kind: str | None) -> None:
    assert status_question(text) == kind
