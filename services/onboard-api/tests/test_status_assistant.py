from datetime import timedelta
from typing import get_args

from fastapi.testclient import TestClient

from assistant.fakes import FakeEvents, FakeReadings, FakeRetriever, Forbidden
from conftest import T0, FakeClock, reading_payload
from onboard_api.assistant.state import AssistantDeps
from onboard_api.dependencies import get_assistant_deps
from onboard_api.schemas.assistant import OperationalEvent
from onboard_api.services.assistant import DISCLAIMER
from onboard_api.schemas.sensors import SensorKind


def _status(client: TestClient) -> dict[str, dict]:
    response = client.get("/astronauts/ana/status")
    assert response.status_code == 200
    body = response.json()
    assert [s["kind"] for s in body["sensors"]] == list(get_args(SensorKind))
    return {s["kind"]: s for s in body["sensors"]}


def test_status_unknown_astronaut_is_404(client: TestClient) -> None:
    response = client.get("/astronauts/nobody/status")
    assert response.status_code == 404
    assert response.json() == {"detail": "Astronaut 'nobody' not found"}


def test_status_no_data(client: TestClient, astronaut: str) -> None:
    response = client.get("/astronauts/ana/status").json()
    assert response["astronaut_id"] == "ana"
    assert response["generated_at"] == "2026-11-14T12:00:00Z"
    for sensor in response["sensors"]:
        assert sensor["status"] == "no_data"
        assert sensor["latest"] is None
        assert sensor["age_seconds"] is None
        assert sensor["config"]["kind"] == sensor["kind"]


def test_status_all_kinds(client: TestClient, astronaut: str, clock: FakeClock) -> None:
    posts = [
        # normal: in range, 60 s old
        reading_payload(kind="heart_rate", value=72, recorded_at="2026-11-14T11:59:00Z"),
        # alert: below normal_min
        reading_payload(kind="spo2", value=90, unit="%", recorded_at="2026-11-14T11:59:00Z"),
        # stale: 2 days old, value would be normal
        reading_payload(kind="urine_ph", value=6.0, unit="pH", recorded_at="2026-11-12T12:00:00Z"),
        # no_range: value_text
        reading_payload(
            kind="urine_color", value=None, value_text="#E0C060", unit="rgb_hex",
            recorded_at="2026-11-14T11:00:00Z",
        ),
        # no_range: no bounds configured
        reading_payload(kind="urine_salinity", value=1.2, unit="g/L", recorded_at="2026-11-14T11:00:00Z"),
        # alert: above normal_max
        reading_payload(
            kind="urine_temperature", value=39, unit="°C", recorded_at="2026-11-14T11:58:00Z"
        ),
    ]
    for payload in posts:
        assert client.post("/readings", json=payload).status_code == 201

    status = _status(client)
    assert status["heart_rate"]["status"] == "normal"
    assert status["heart_rate"]["age_seconds"] == 60
    assert status["heart_rate"]["latest"]["value"] == 72
    assert status["spo2"]["status"] == "alert"
    assert status["urine_ph"]["status"] == "stale"
    assert status["urine_ph"]["latest"]["value"] == 6.0
    assert status["urine_ph"]["age_seconds"] == 2 * 86400
    assert status["urine_color"]["status"] == "no_range"
    assert status["urine_salinity"]["status"] == "no_range"
    assert status["urine_temperature"]["status"] == "alert"
    assert status["muscle_density"]["status"] == "no_data"

    # Time passes: the heart rate reading becomes stale (300 s).
    clock.now = T0 + timedelta(seconds=301)
    assert _status(client)["heart_rate"]["status"] == "stale"


def test_status_uses_latest_reading_and_clamps_future(
    client: TestClient, astronaut: str
) -> None:
    client.post("/readings", json=reading_payload(value=130, recorded_at="2026-11-14T11:50:00Z"))
    # Recorded 5 s in the future (capture clock slightly ahead).
    client.post("/readings", json=reading_payload(value=80, recorded_at="2026-11-14T12:00:05Z"))
    heart_rate = _status(client)["heart_rate"]
    assert heart_rate["latest"]["value"] == 80
    assert heart_rate["age_seconds"] == 0
    assert heart_rate["status"] == "normal"


def test_threshold_change_changes_status(client: TestClient, astronaut: str) -> None:
    client.post("/readings", json=reading_payload(value=95))
    assert _status(client)["heart_rate"]["status"] == "normal"

    response = client.put(
        "/sensors/heart_rate",
        json={
            "unit": "bpm",
            "stale_after_seconds": 300,
            "normal_min": None,  # single bound
            "normal_max": 90,
            "range_role": "health",
            "provisional": True,
            "range_source": "test",
        },
    )
    assert response.status_code == 200
    assert _status(client)["heart_rate"]["status"] == "alert"

    # No stale_after_seconds: never stale.
    response = client.put(
        "/sensors/heart_rate",
        json={
            "unit": "bpm",
            "stale_after_seconds": None,
            "normal_min": None,
            "normal_max": None,
            "range_role": "health",
            "provisional": True,
            "range_source": None,
        },
    )
    assert response.status_code == 200
    assert _status(client)["heart_rate"]["status"] == "no_range"


def _offline_assistant(client: TestClient, events=None) -> None:
    """Fake integrations: the test app must never reach a real Ollama or ChromaDB."""
    client.app.dependency_overrides[get_assistant_deps] = lambda: AssistantDeps(
        llm=Forbidden("llm"),
        retriever=FakeRetriever([]),
        readings=FakeReadings(),
        events=FakeEvents(events),
    )


def test_assistant_vague_message_clarifies(client: TestClient) -> None:
    _offline_assistant(client)
    response = client.post("/assistant/messages", json={"message": "Hola", "astronaut_id": "ana"})
    assert response.status_code == 200
    body = response.json()
    assert body["workflow"] == "clarify"
    assert body["needs_clarification"] is True
    assert body["reply"].count("?") == 1
    assert body["clarifying_question"] == body["reply"]


def test_assistant_confirmed_cabin_event_is_immediate(client: TestClient) -> None:
    event = OperationalEvent(
        id="co2-1", type="cabin_co2", origin="ship:eclss", occurred_at=T0,
        status="active", provenance="confirmed",
    )
    _offline_assistant(client, [event])
    response = client.post("/assistant/messages", json={"message": "Hola", "astronaut_id": "ana"})
    assert response.status_code == 200
    body = response.json()
    assert body["workflow"] == "medical"
    assert body["urgency"] == "immediate"
    assert body["disclaimer"] == DISCLAIMER


def test_assistant_empty_message_is_422(client: TestClient) -> None:
    assert client.post("/assistant/messages", json={"message": ""}).status_code == 422
