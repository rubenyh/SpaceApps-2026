"""Ground receiver and read API for contracts/case-report v1."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ground_api.config import Settings
from ground_api.main import create_app
from ground_api.schemas import CaseReportV1
from ground_api.telemetry import get_clock

EXAMPLES = sorted((Path(__file__).resolve().parents[3] / "contracts" / "case-report" / "examples").glob("*.json"))
BASIC = json.loads(EXAMPLES[0].read_text("utf-8"))
INCIDENT = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "telemetry" / "examples" / "batch-incident.json").read_text("utf-8")
)
INCIDENT_ID = INCIDENT["incident_updates"][0]["incident_id"]
T0 = datetime(2026, 11, 14, 18, 5, 0, tzinfo=UTC)


class Clock:
    now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(tmp_path: Path, clock: Clock):
    app = create_app(Settings(db_path=tmp_path / "ground.db"))
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        yield c


def report(**overrides: object) -> dict:
    return {**BASIC, "report_id": str(uuid.uuid4()), **overrides}


def test_examples_exist() -> None:
    assert EXAMPLES


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_contract_examples_parse(path: Path) -> None:
    raw = json.loads(path.read_text("utf-8"))
    assert CaseReportV1.model_validate(raw).model_dump(mode="json") == raw


def test_resend_is_idempotent_and_returns_first_receipt(client: TestClient, clock: Clock) -> None:
    first = client.post("/case-reports/v1", json=BASIC)
    assert first.status_code == 200
    assert first.json() == {"report_id": BASIC["report_id"], "received_at": "2026-11-14T18:05:00Z"}
    clock.now = T0 + timedelta(minutes=3)  # ack was lost; the ship resends
    assert client.post("/case-reports/v1", json={**BASIC, "text": "changed"}).json() == first.json()
    assert client.get(f"/case-reports/{BASIC['report_id']}").json() == {**BASIC, "received_at": "2026-11-14T18:05:00Z"}
    assert len(client.get("/case-reports").json()) == 1
    assert client.get("/case-reports/unknown").status_code == 404


def test_invalid_report_422(client: TestClient) -> None:
    assert client.post("/case-reports/v1", json={**BASIC, "extra": 1}).status_code == 422
    assert client.post("/case-reports/v1", json={**BASIC, "urgency": "panic"}).status_code == 422


def test_list_newest_first_with_filters(client: TestClient, clock: Clock) -> None:
    ids = []
    for minute, overrides in enumerate([{}, {"astronaut_id": "bea"}, {"urgency": "immediate", "incident_id": "i-1"}]):
        clock.now = T0 + timedelta(minutes=minute)
        ids.append(client.post("/case-reports/v1", json=report(**overrides)).json()["report_id"])

    def listed(**params: str) -> list[str]:
        return [r["report_id"] for r in client.get("/case-reports", params=params).json()]

    assert listed() == ids[::-1]
    assert listed(astronaut_id="ana") == [ids[2], ids[0]]
    assert listed(urgency="immediate") == listed(incident_id="i-1") == [ids[2]]
    assert client.get("/case-reports", params={"urgency": "panic"}).status_code == 422


def test_incident_lists_its_report_ids_and_demo_reset_deletes_them(client: TestClient, clock: Clock) -> None:
    client.post("/telemetry/v1/batches", json=INCIDENT)
    older = client.post("/case-reports/v1", json=report(incident_id=INCIDENT_ID, astronaut_id="ast-01")).json()
    clock.now = T0 + timedelta(minutes=1)
    newer = client.post("/case-reports/v1", json=report(incident_id=INCIDENT_ID, astronaut_id="ast-01")).json()
    client.post("/case-reports/v1", json=report(incident_id=INCIDENT_ID, ship_id="ship-02"))
    kept = client.post("/case-reports/v1", json=report()).json()  # astronaut ana
    assert client.get(f"/incidents/{INCIDENT_ID}").json()["report_ids"] == [newer["report_id"], older["report_id"]]

    client.app.state.settings.demo_controls_enabled = True
    assert client.delete("/demo/incidents", params={"astronaut_id": "ast-01"}).json() == {"deleted": 1}
    remaining = [r["report_id"] for r in client.get("/case-reports").json()]
    assert newer["report_id"] not in remaining and older["report_id"] not in remaining
    assert kept["report_id"] in remaining
