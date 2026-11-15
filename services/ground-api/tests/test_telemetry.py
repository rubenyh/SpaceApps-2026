import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ground_api.config import Settings
from ground_api.main import create_app
from ground_api.schemas import TelemetryBatch
from ground_api.telemetry import get_clock

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "contracts" / "telemetry" / "examples"
EXAMPLES = sorted(EXAMPLES_DIR.glob("*.json"))
BASIC = json.loads((EXAMPLES_DIR / "batch-basic.json").read_text("utf-8"))
INCIDENT = json.loads((EXAMPLES_DIR / "batch-incident.json").read_text("utf-8"))
NO_UPDATES = {"incident_updates_accepted": 0, "incident_updates_duplicates": 0}
# 30 s after the basic batch was sent.
T0 = datetime(2026, 11, 14, 18, 2, 45, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(tmp_path: Path, clock: FakeClock):
    app = create_app(Settings(db_path=tmp_path / "nested" / "ground.db"))
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        yield c


def batch(**overrides: object) -> dict:
    data = copy.deepcopy(BASIC)
    data["batch_id"] = str(uuid.uuid4())
    data.update(overrides)
    return data


def test_examples_exist() -> None:
    assert EXAMPLES


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_contract_examples_parse(path: Path) -> None:
    TelemetryBatch.model_validate_json(path.read_text("utf-8"))


def test_health_and_empty_state(client: TestClient) -> None:
    assert client.get("/").json() == {"status": "ok"}
    assert client.get("/link").json() == {
        "ship_id": None,
        "last_batch_sent_at": None,
        "last_batch_received_at": None,
        "seconds_since_last_batch": None,
        "batches_received": 0,
        "readings_received": 0,
    }
    assert client.get("/telemetry/v1/cursor", params={"ship_id": "ship-01"}).json() == {
        "last_reading_id": None
    }
    assert client.get("/crew").json() == []
    assert client.get("/alerts").json() == []


def test_batch_accepted_and_duplicate_batch_stored_once(client: TestClient) -> None:
    response = client.post("/telemetry/v1/batches", json=BASIC)
    assert response.status_code == 202
    assert response.json() == {"accepted": 2, "duplicates": 0, **NO_UPDATES}
    again = client.post("/telemetry/v1/batches", json=BASIC)
    assert again.status_code == 202
    assert again.json() == {"accepted": 0, "duplicates": 2, **NO_UPDATES}
    link = client.get("/link").json()
    assert link["batches_received"] == 1
    assert link["readings_received"] == 2
    assert link["ship_id"] == "ship-01"
    assert link["last_batch_sent_at"] == "2026-11-14T18:02:15Z"
    assert link["seconds_since_last_batch"] == 0
    assert len(client.get("/alerts").json()) == 1


def test_duplicate_reading_ids_ignored(client: TestClient) -> None:
    client.post("/telemetry/v1/batches", json=BASIC)
    response = client.post("/telemetry/v1/batches", json=batch())
    assert response.json() == {"accepted": 0, "duplicates": 2, **NO_UPDATES}
    assert client.get("/link").json()["batches_received"] == 2
    assert len(client.get("/astronauts/ast-02/readings").json()) == 1
    assert len(client.get("/alerts").json()) == 1


@pytest.mark.parametrize(
    "body",
    [
        {**BASIC, "schema_version": 2},
        {**BASIC, "batch_id": "not-a-uuid"},
        {**BASIC, "sent_at": "2026-11-14T18:02:15"},  # no offset
        {**BASIC, "extra": 1},
        {k: v for k, v in BASIC.items() if k != "sensors"},
        {**BASIC, "readings": [{**BASIC["readings"][0], "kind": "blood_sugar"}]},
        # Incident updates carry only contract fields: no message or report text.
        {**BASIC, "incident_updates": [{**INCIDENT["incident_updates"][0], "reply": "text"}]},
        {**BASIC, "incident_updates": [{**INCIDENT["incident_updates"][0], "type": "deleted"}]},
    ],
)
def test_invalid_batch_422(client: TestClient, body: dict) -> None:
    assert client.post("/telemetry/v1/batches", json=body).status_code == 422
    assert client.get("/link").json()["batches_received"] == 0


def test_cursor_per_ship(client: TestClient) -> None:
    client.post("/telemetry/v1/batches", json=BASIC)
    assert client.get("/telemetry/v1/cursor", params={"ship_id": "ship-01"}).json() == {
        "last_reading_id": 42
    }
    assert client.get("/telemetry/v1/cursor", params={"ship_id": "ship-02"}).json() == {
        "last_reading_id": None
    }


def test_crew_status_with_ground_clock(client: TestClient, clock: FakeClock) -> None:
    client.post("/telemetry/v1/batches", json=BASIC)
    crew = {m["astronaut_id"]: m for m in client.get("/crew").json()}
    assert crew["ast-01"]["display_name"] == "Demo Uno"
    # Sensors present in the batch, in SensorKind order.
    kinds = [s["kind"] for s in crew["ast-02"]["sensors"]]
    assert kinds == ["heart_rate", "urine_color", "urine_temperature"]
    hr = crew["ast-02"]["sensors"][0]
    assert hr["status"] == "alert"
    assert hr["age_seconds"] == 35
    assert hr["latest"]["ground_received_at"] == "2026-11-14T18:02:45Z"
    assert hr["config"]["normal_max"] == 100
    by_kind = {s["kind"]: s for s in crew["ast-01"]["sensors"]}
    assert by_kind["urine_color"]["status"] == "no_range"
    assert by_kind["heart_rate"]["status"] == "no_data"

    clock.now = T0 + timedelta(seconds=300)  # link delay counts toward staleness
    hr = client.get("/crew").json()[1]["sensors"][0]
    assert (hr["status"], hr["age_seconds"]) == ("stale", 335)
    assert client.get("/link").json()["seconds_since_last_batch"] == 300


def test_heartbeat_keeps_configs_and_crew(client: TestClient) -> None:
    client.post("/telemetry/v1/batches", json=BASIC)
    heartbeat = json.loads((EXAMPLES_DIR / "batch-heartbeat.json").read_text("utf-8"))
    assert client.post("/telemetry/v1/batches", json=heartbeat).json() == {
        "accepted": 0,
        "duplicates": 0,
        **NO_UPDATES,
    }
    crew = client.get("/crew").json()
    assert [m["astronaut_id"] for m in crew] == ["ast-01", "ast-02"]
    assert len(crew[0]["sensors"]) == 3
    assert client.get("/link").json()["last_batch_sent_at"] == "2026-11-14T18:02:20Z"


def reading(id: int, kind: str, value: float | None, value_text: str | None = None, unit: str = "x") -> dict:
    return {
        "id": id, "astronaut_id": "ast-01", "kind": kind, "value": value, "value_text": value_text,
        "unit": unit, "recorded_at": f"2026-11-14T18:00:{id:02d}Z",
        "received_at": f"2026-11-14T18:00:{id:02d}Z", "quality": "good", "source": "test",
    }


def sensor(kind: str, lo: float | None, hi: float | None, role: str = "health") -> dict:
    return {
        "kind": kind, "unit": "x", "stale_after_seconds": None, "normal_min": lo,
        "normal_max": hi, "range_role": role, "provisional": True, "range_source": None,
    }


def test_alerts_rules(client: TestClient) -> None:
    body = batch(
        sensors=[
            sensor("heart_rate", 60, 100),
            sensor("spo2", 95, None),
            sensor("urine_temperature", 32, 38, role="sample_validity"),
            sensor("urine_radiation_marker", 0, 1),
            sensor("urine_color", None, None),
        ],
        readings=[
            reading(1, "heart_rate", 112),
            reading(2, "heart_rate", 80),
            reading(3, "spo2", 90),
            reading(4, "urine_temperature", 40),
            reading(5, "urine_radiation_marker", 5),
            reading(6, "urine_color", None, "#D9C24A"),
            reading(7, "heart_rate", 50),
        ],
    )
    assert client.post("/telemetry/v1/batches", json=body).json()["accepted"] == 7
    alerts = client.get("/alerts").json()
    assert [(a["reading"]["id"], a["side"]) for a in alerts] == [(7, "low"), (3, "low"), (1, "high")]
    assert (alerts[2]["normal_min"], alerts[2]["normal_max"]) == (60, 100)
    assert alerts[0]["reading"]["ground_received_at"] == "2026-11-14T18:02:45Z"
    assert len(client.get("/alerts", params={"limit": 1}).json()) == 1
    assert client.get("/alerts", params={"limit": 501}).status_code == 422


def test_astronaut_readings_filters(client: TestClient) -> None:
    body = batch(readings=[reading(1, "heart_rate", 70), reading(2, "spo2", 98), reading(3, "heart_rate", 72)])
    client.post("/telemetry/v1/batches", json=body)
    rows = client.get("/astronauts/ast-01/readings").json()
    assert [r["id"] for r in rows] == [3, 2, 1]
    rows = client.get("/astronauts/ast-01/readings", params={"kind": "heart_rate", "limit": 1}).json()
    assert [r["id"] for r in rows] == [3]
    rows = client.get("/astronauts/ast-01/readings", params={"since": "2026-11-14T18:00:02Z"}).json()
    assert [r["id"] for r in rows] == [3, 2]
    assert client.get("/astronauts/nobody/readings").status_code == 404
    assert client.get("/astronauts/ast-01/readings", params={"limit": 1001}).status_code == 422


def test_cors_allows_base_app(client: TestClient) -> None:
    response = client.get("/crew", headers={"Origin": "http://localhost:1421"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:1421"


INCIDENT_ID = INCIDENT["incident_updates"][0]["incident_id"]
CREATED, ACKED = INCIDENT["incident_updates"]
RULES = CREATED["matched_rules"]


def test_incident_updates_stored_once_despite_retries(client: TestClient, clock: FakeClock) -> None:
    clock.now = datetime(2026, 11, 14, 18, 10, 5, tzinfo=UTC)
    response = client.post("/telemetry/v1/batches", json=INCIDENT)
    assert response.status_code == 202
    assert response.json() == {
        "accepted": 0, "duplicates": 0, "incident_updates_accepted": 2, "incident_updates_duplicates": 0
    }
    # Ground stored it but the response was lost: onboard retries the same batch, then
    # (after a restart) sends the same updates under a new batch_id.
    clock.now += timedelta(minutes=1)
    for body in (INCIDENT, {**INCIDENT, "batch_id": str(uuid.uuid4())}):
        assert client.post("/telemetry/v1/batches", json=body).json()["incident_updates_duplicates"] == 2

    [listed] = client.get("/incidents").json()
    received = "2026-11-14T18:10:05Z"  # first delivery, stored apart from the onboard time
    assert listed == client.get(f"/incidents/{INCIDENT_ID}").json() == {
        "ship_id": "ship-01",
        "id": INCIDENT_ID,
        "astronaut_id": "ast-01",
        "began_at": "2026-11-14T18:05:00Z",
        "urgency": "immediate",
        "protocol_id": "respiratory-distress",
        "protocol_version": "1.0",
        "matched_rules": RULES,
        "action": CREATED["action"],
        "acknowledgments": [
            {"acknowledged_by": "ast-02", "acknowledged_at": "2026-11-14T18:06:30Z", "received_at": received}
        ],
        "updates": [
            {"id": CREATED["id"], "type": "created", "occurred_at": "2026-11-14T18:05:00Z",
             "received_at": received, "acknowledged_by": None},
            {"id": ACKED["id"], "type": "acknowledged", "occurred_at": "2026-11-14T18:06:30Z",
             "received_at": received, "acknowledged_by": "ast-02"},
        ],
    }
    assert client.get("/incidents/unknown").status_code == 404


def test_offline_ack_arrives_later_with_its_onboard_time(client: TestClient, clock: FakeClock) -> None:
    clock.now = datetime(2026, 11, 14, 18, 5, 1, tzinfo=UTC)
    client.post("/telemetry/v1/batches", json=batch(readings=[], incident_updates=[CREATED]))
    clock.now = datetime(2026, 11, 14, 18, 20, 0, tzinfo=UTC)  # link was down for the ack
    client.post("/telemetry/v1/batches", json=batch(readings=[], incident_updates=[ACKED]))
    incident = client.get(f"/incidents/{INCIDENT_ID}").json()
    assert incident["began_at"] == "2026-11-14T18:05:00Z"
    [ack] = incident["acknowledgments"]
    assert ack == {
        "acknowledged_by": "ast-02",
        "acknowledged_at": "2026-11-14T18:06:30Z",
        "received_at": "2026-11-14T18:20:00Z",
    }
    for update in incident["updates"]:
        assert update["received_at"] >= update["occurred_at"]
    assert [u["received_at"] for u in incident["updates"]] == ["2026-11-14T18:05:01Z", "2026-11-14T18:20:00Z"]


def test_incidents_newest_first_and_began_at_waits_for_created(client: TestClient, clock: FakeClock) -> None:
    clock.now = datetime(2026, 11, 14, 19, 0, 0, tzinfo=UTC)
    later = {**CREATED, "id": str(uuid.uuid4()), "incident_id": "inc-2", "occurred_at": "2026-11-14T18:30:00Z"}
    orphan_ack = {**ACKED, "id": str(uuid.uuid4()), "incident_id": "inc-3"}
    client.post("/telemetry/v1/batches", json=batch(readings=[], incident_updates=[CREATED, later, orphan_ack]))
    listed = client.get("/incidents").json()
    assert [(i["id"], i["began_at"]) for i in listed] == [
        ("inc-2", "2026-11-14T18:30:00Z"), (INCIDENT_ID, "2026-11-14T18:05:00Z"), ("inc-3", None)
    ]
    created_3 = {**CREATED, "id": str(uuid.uuid4()), "incident_id": "inc-3"}
    client.post("/telemetry/v1/batches", json=batch(readings=[], incident_updates=[created_3]))
    assert client.get("/incidents/inc-3").json()["began_at"] == "2026-11-14T18:05:00Z"


def test_demo_reset_is_off_by_default_then_deletes_one_astronaut(client: TestClient) -> None:
    client.post("/telemetry/v1/batches", json=batch(readings=[], incident_updates=[CREATED, ACKED]))
    who = CREATED["astronaut_id"]
    assert client.delete("/demo/incidents", params={"astronaut_id": who}).status_code == 403
    client.app.state.settings.demo_controls_enabled = True
    assert client.delete("/demo/incidents", params={"astronaut_id": "nobody"}).json() == {"deleted": 0}
    assert client.delete("/demo/incidents", params={"astronaut_id": who}).json() == {"deleted": 1}
    assert client.get("/incidents").json() == []
    # Updates are gone too: the same ids are accepted again as new.
    accepted = client.post("/telemetry/v1/batches", json=batch(readings=[], incident_updates=[CREATED]))
    assert accepted.json()["incident_updates_accepted"] == 1
