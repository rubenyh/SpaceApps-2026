"""Case report drafts, crew send and delivery to ground (contracts/case-report)."""

import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator  # locked through chromadb

from onboard_api.dependencies import get_assistant_responder
from onboard_api.routers.case_reports import get_draft_store
from onboard_api.schemas.assistant import AssistantResponse, CaseReport, SnapshotReading
from onboard_api.schemas.case_reports import CaseReportV1
from onboard_api.telemetry import publisher as publisher_module
from onboard_api.telemetry.publisher import TelemetryPublisher

from conftest import T0

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "case-report"
SCHEMA = Draft202012Validator(json.loads((CONTRACT / "case-report.v1.schema.json").read_text("utf-8")))
EXAMPLES = sorted((CONTRACT / "examples").glob("*.json"))
GROUND_T = T0 + timedelta(minutes=5)
READING = SnapshotReading(
    id=1, kind="heart_rate", value=112, unit="bpm", recorded_at=T0 - timedelta(seconds=30),
    received_at=T0 - timedelta(seconds=29), quality="good", source="simulated:pulse-ox",
    simulated=True, freshness="current", age_seconds=30,
)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_contract_examples_parse_and_match_schema(path: Path) -> None:
    raw = json.loads(path.read_text("utf-8"))
    SCHEMA.validate(raw)
    assert CaseReportV1.model_validate(raw).model_dump(mode="json").keys() == raw.keys()


class FakeGround:
    """Telemetry endpoints plus the ground case-report receiver (dedup by report id)."""

    def __init__(self) -> None:
        self.up = True
        self.reports: dict[str, dict] = {}
        self.posts: list[str] = []
        self.status = 200
        self.lose_ack = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("link down", request=request)
        if request.url.path == "/telemetry/v1/cursor":
            return httpx.Response(200, json={"last_reading_id": None})
        if request.url.path == "/telemetry/v1/batches":
            return httpx.Response(202, json={})
        body = json.loads(request.content)
        self.posts.append(body["report_id"])
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "bad report"})
        SCHEMA.validate(body)
        stored = self.reports.setdefault(body["report_id"], {**body, "received_at": GROUND_T.isoformat()})
        if self.lose_ack:  # stored, but the answer never reaches the ship
            return httpx.Response(500)
        return httpx.Response(200, json={"report_id": body["report_id"], "received_at": stored["received_at"]})


def draft(client: TestClient, urgency: str = "review_required", astronaut_id: str = "ana", assessed_at=T0) -> dict:
    report_id = str(uuid.uuid4())
    response = AssistantResponse(
        reply="Limit movement.", workflow="medical", needs_clarification=False, urgency=urgency,
        action="Limit movement and monitor", protocol_id="dizziness", assessed_at=assessed_at,
        report=CaseReport(text="Case report", id=report_id, readings=[READING]),
    )
    client.app.dependency_overrides[get_assistant_responder] = lambda: lambda _req: response.model_copy(deep=True)
    body = client.post("/assistant/messages", json={"message": "dizzy", "astronaut_id": astronaut_id}).json()
    assert body["report"]["id"] == report_id
    return body


def step(ground: FakeGround, db_path: Path, times: int = 1) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(ground), base_url="http://ground") as http:
            pub = TelemetryPublisher(http, db_path, "ship-01", 5, clock=lambda: T0)  # new instance: a restart
            for _ in range(times):
                await pub.step()

    asyncio.run(scenario())


def status(client: TestClient, report_id: str) -> dict:
    return client.get(f"/case-reports/{report_id}").json()


def test_draft_stored_then_send_is_idempotent(client: TestClient, astronaut: str, clock) -> None:
    body = draft(client)
    report_id = body["report"]["id"]
    assert body["report"]["transmission"] == "draft"
    assert status(client, report_id) == {
        "id": report_id, "status": "draft", "created_at": "2026-11-14T12:00:00Z",
        "queued_at": None, "received_at": None, "error": None,
    }
    sent = client.post(f"/case-reports/{report_id}/send", json={"sent_by": "ana"}).json()
    assert (sent["status"], sent["queued_at"]) == ("queued", "2026-11-14T12:00:00Z")
    clock.now = T0 + timedelta(minutes=1)
    assert client.post(f"/case-reports/{report_id}/send", json={}).json() == sent
    assert client.post("/case-reports/nope/send", json={}).status_code == 404
    assert client.get("/case-reports/nope").status_code == 404


def test_draft_without_assessed_at_uses_draft_time(client: TestClient, astronaut: str, db_path: Path) -> None:
    report_id = draft(client, assessed_at=None)["report"]["id"]
    client.post(f"/case-reports/{report_id}/send", json={})
    ground = FakeGround()
    step(ground, db_path)
    assert ground.reports[report_id]["assessed_at"] == ground.reports[report_id]["created_at"]


def test_storage_failure_keeps_reply(client: TestClient, astronaut: str) -> None:
    def broken(*_args) -> str:
        raise RuntimeError("disk gone")

    client.app.dependency_overrides[get_draft_store] = lambda: broken
    body = draft(client)
    assert body["reply"] == "Limit movement." and body["report"]["transmission"] == "draft"


def test_publisher_delivers_with_ground_receipt_time(client: TestClient, astronaut: str, db_path: Path, monkeypatch) -> None:
    urgent = draft(client, urgency="immediate")
    report_id = urgent["report"]["id"]
    other = draft(client)["report"]["id"]
    for rid in (report_id, other):
        client.post(f"/case-reports/{rid}/send", json={"sent_by": "ana"})
    ground = FakeGround()
    monkeypatch.setattr(publisher_module, "REPORT_BATCH_SIZE", 1)

    async def first_step() -> bool:
        async with httpx.AsyncClient(transport=httpx.MockTransport(ground), base_url="http://ground") as http:
            return await TelemetryPublisher(http, db_path, "ship-01", 5).step()

    assert asyncio.run(first_step()) is True  # full report batch: more may be waiting
    step(ground, db_path)
    assert ground.posts == [report_id, other]  # oldest queued first
    sent = ground.reports[report_id]
    assert (sent["incident_id"], sent["sent_by"], sent["urgency"]) == (urgent["incident"]["id"], "ana", "immediate")
    assert sent["readings"] == [READING.model_dump(mode="json")] and sent["text"] == urgent["report"]["text"]
    assert status(client, report_id)["status"] == "received"
    assert status(client, report_id)["received_at"] == "2026-11-14T12:05:00Z"


def test_paused_holds_reports_and_restart_still_delivers(
    client: TestClient, astronaut: str, db_path: Path, monkeypatch
) -> None:
    report_id = draft(client)["report"]["id"]
    client.post(f"/case-reports/{report_id}/send", json={})
    ground = FakeGround()

    async def stop(_self, _delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(TelemetryPublisher, "_wait", stop)

    async def paused_run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(ground), base_url="http://ground") as http:
            pub = TelemetryPublisher(http, db_path, "ship-01", 5)
            pub.paused = True
            with pytest.raises(asyncio.CancelledError):
                await pub.run()

    asyncio.run(paused_run())
    ground.up = False
    with pytest.raises(httpx.ConnectError):
        step(ground, db_path)
    assert ground.posts == [] and status(client, report_id)["status"] == "queued"
    ground.up = True
    step(ground, db_path)  # a fresh publisher on the same DB
    assert status(client, report_id)["status"] == "received"


def test_lost_ack_is_retried_and_stored_once(client: TestClient, astronaut: str, db_path: Path) -> None:
    report_id = draft(client)["report"]["id"]
    client.post(f"/case-reports/{report_id}/send", json={})
    ground = FakeGround()
    ground.lose_ack = True
    with pytest.raises(httpx.HTTPStatusError):
        step(ground, db_path)
    assert status(client, report_id)["status"] == "queued"
    ground.lose_ack = False
    step(ground, db_path)
    assert ground.posts == [report_id, report_id] and list(ground.reports) == [report_id]
    assert status(client, report_id)["status"] == "received"


def test_rejected_report_fails_with_reason_and_can_be_resent(client: TestClient, astronaut: str, db_path: Path) -> None:
    report_id = draft(client)["report"]["id"]
    client.post(f"/case-reports/{report_id}/send", json={})
    ground = FakeGround()
    ground.status = 422
    step(ground, db_path)  # does not raise: the loop is not held by a rejected report
    failed = status(client, report_id)
    assert failed["status"] == "failed" and failed["error"].startswith("ground rejected (HTTP 422): ")
    resent = client.post(f"/case-reports/{report_id}/send", json={}).json()
    assert (resent["status"], resent["error"]) == ("queued", None)


@pytest.mark.parametrize("code", [404, 429, 503])
def test_transient_ground_errors_keep_report_queued(code: int, client: TestClient, astronaut: str, db_path: Path) -> None:
    report_id = draft(client)["report"]["id"]
    client.post(f"/case-reports/{report_id}/send", json={})
    ground = FakeGround()
    ground.status = code
    with pytest.raises(httpx.HTTPStatusError):
        step(ground, db_path)
    assert status(client, report_id)["status"] == "queued"


def test_demo_reset_deletes_case_reports(client: TestClient, astronaut: str) -> None:
    client.post("/astronauts", json={"id": "bea", "display_name": "Bea"})
    mine, theirs = draft(client)["report"]["id"], draft(client, astronaut_id="bea")["report"]["id"]
    client.app.state.settings.demo_controls_enabled = True
    assert client.delete("/demo/incidents", params={"astronaut_id": "ana"}).status_code == 200
    assert client.get(f"/case-reports/{mine}").status_code == 404
    assert status(client, theirs)["status"] == "draft"
