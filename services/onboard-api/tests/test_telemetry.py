import asyncio
import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from assistant.fakes import Forbidden
from assistant.test_post_cases import post
from onboard_api.repositories.database import connect, to_db_timestamp
from onboard_api.repositories.incidents import IncidentRepository
from onboard_api.telemetry import publisher as publisher_module
from onboard_api.telemetry.publisher import TelemetryBatch, TelemetryPublisher

from conftest import T0, reading_payload

EXAMPLES = sorted((Path(__file__).resolve().parents[3] / "contracts" / "telemetry" / "examples").glob("*.json"))


def _keys(value: object) -> object:
    """Nested key structure, so a renamed or missing field fails the fixture test."""
    if isinstance(value, dict):
        return {k: _keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_keys(v) for v in value]
    return None


def test_examples_exist() -> None:
    assert EXAMPLES


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_contract_examples_parse(path: Path) -> None:
    raw = json.loads(path.read_text("utf-8"))
    batch = TelemetryBatch.model_validate(raw)
    # exclude_unset: incident_updates is optional in v1 (absent in older examples).
    assert _keys(batch.model_dump(mode="json", exclude_unset=True)) == _keys(raw)


class FakeGround:
    def __init__(self) -> None:
        self.up = True
        self.batches: list[dict] = []
        self.cursor: int | None = None
        self.status = 202

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("link down", request=request)
        if request.url.path == "/telemetry/v1/cursor":
            return httpx.Response(200, json={"last_reading_id": self.cursor})
        self.batches.append(json.loads(request.content))
        return httpx.Response(self.status, json={"accepted": 0, "duplicates": 0})


def test_publisher_sends_after_cursor_and_retries_same_batch(
    client: TestClient, astronaut: str, db_path: Path
) -> None:
    for minute in range(3):
        response = client.post(
            "/readings", json=reading_payload(recorded_at=f"2026-11-14T11:5{minute}:00Z")
        )
        assert response.status_code == 201
    ground = FakeGround()
    ground.cursor = 1  # ground already has reading 1

    async def scenario() -> TelemetryPublisher:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(ground), base_url="http://ground"
        ) as http:
            pub = TelemetryPublisher(http, db_path, "ship-01", 5, clock=lambda: T0)
            assert await pub.step() is False
            # Link lost: the step raises (run() catches it), the batch stays pending.
            client.post("/readings", json=reading_payload(recorded_at="2026-11-14T11:59:00Z"))
            ground.up = False
            with pytest.raises(httpx.ConnectError):
                await pub.step()
            pending_id = str(pub.pending.batch_id)
            ground.up = True
            await pub.step()
            assert ground.batches[-1]["batch_id"] == pending_id
            return pub

    pub = asyncio.run(scenario())
    first, retried = ground.batches
    assert [r["id"] for r in first["readings"]] == [2, 3]
    assert [a["id"] for a in first["astronauts"]] == ["ana"]
    assert len(first["sensors"]) == 8
    assert [r["id"] for r in retried["readings"]] == [4]
    assert pub.cursor == 4
    TelemetryBatch.model_validate(first)


def test_run_backs_off_and_never_raises(db_path: Path, client: TestClient, monkeypatch) -> None:
    ground = FakeGround()
    ground.up = False
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(publisher_module.asyncio, "sleep", fake_sleep)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(ground), base_url="http://ground"
        ) as http:
            with pytest.raises(asyncio.CancelledError):
                await TelemetryPublisher(http, db_path, "ship-01", 5).run()

    asyncio.run(scenario())
    assert delays == [10, 20, 40]


def test_lifespan_without_telemetry_starts_nothing(make_client: Callable[[], TestClient]) -> None:
    # Telemetry disabled in test settings: no task, no network.
    assert not hasattr(make_client().app.state, "telemetry_publisher")


SECRET = "The purple giraffe hums in module seven"


def urgent_incident(client: TestClient, db_path: Path) -> dict:
    """Urgent assistant message (offline: no LLM, no retriever) that opens an incident."""
    request = {"astronaut_id": "ana", "message": f"I can't breathe. {SECRET}.", "reported_by": "ana"}
    body = post(client, db_path, request, llm=Forbidden("llm"), retriever=Forbidden("retriever"))[0]
    assert body["urgency"] == "immediate" and body["incident"]["recorded"]
    return body


def incident(db_path: Path, incident_id: str):
    conn = connect(db_path)
    try:
        return IncidentRepository(conn).get(incident_id)  # telemetry enabled
    finally:
        conn.close()


def run_steps(ground: "FakeGround", db_path: Path, *steps: Callable) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(ground), base_url="http://ground") as http:
            for step in steps:
                await step(http)

    asyncio.run(scenario())


def test_batch_carries_no_message_reply_or_report_text(client: TestClient, astronaut: str, db_path: Path) -> None:
    body = urgent_incident(client, db_path)
    batch = TelemetryPublisher(httpx.AsyncClient(), db_path, "ship-01", 5)._build_batch()
    sent = batch.model_dump_json()
    [update] = batch.incident_updates
    assert update.incident_id == body["incident"]["id"] and update.type == "created"
    assert update.action == body["action"] and update.urgency == "immediate"
    texts = [SECRET, body["reply"], *([body["report"]["text"]] if body["report"] else [])]
    texts += [f["detail"] for f in body["findings"] if f.get("detail")]
    for text in texts:
        assert text not in sent


def test_incident_queued_offline_then_delivered_after_reconnect(
    client: TestClient, astronaut: str, db_path: Path
) -> None:
    incident_id = urgent_incident(client, db_path)["incident"]["id"]
    ground = FakeGround()
    ground.cursor = 0
    delivered_at = T0 + timedelta(minutes=10)
    pub_clock = [T0]

    async def offline(http: httpx.AsyncClient) -> None:
        pub = TelemetryPublisher(http, db_path, "ship-01", 5, clock=lambda: pub_clock[0])
        ground.up = False
        with pytest.raises(httpx.ConnectError):
            await pub.step()
        ground.up, ground.status = True, 503  # ground reachable but failing: still not confirmed
        with pytest.raises(httpx.HTTPStatusError):
            await pub.step()
        assert incident(db_path, incident_id).ground_delivery == "queued"
        ground.status = 202
        pub_clock[0] = delivered_at
        await pub.step()

    run_steps(ground, db_path, offline)
    assert [u["id"] for u in ground.batches[-1]["incident_updates"]] == [
        e.id for e in incident(db_path, incident_id).events
    ]
    stored = incident(db_path, incident_id)
    assert stored.ground_delivery == "delivered"
    assert [e.delivered_at for e in stored.events] == [delivered_at]


def test_queued_update_survives_restart(
    make_client: Callable[[], TestClient], db_path: Path
) -> None:
    client = make_client()
    assert client.post("/astronauts", json={"id": "ana", "display_name": "Ana"}).status_code == 201
    incident_id = urgent_incident(client, db_path)["incident"]["id"]
    ground = FakeGround()
    ground.status = 503  # ground answers but fails: the batch is not confirmed

    async def before_restart(http: httpx.AsyncClient) -> None:
        pub = TelemetryPublisher(http, db_path, "ship-01", 5, clock=lambda: T0)
        with pytest.raises(httpx.HTTPStatusError):
            await pub.step()

    run_steps(ground, db_path, before_restart)
    assert incident(db_path, incident_id).ground_delivery == "queued"
    make_client()  # onboard-api restarts; the in-memory pending batch is gone
    ground.status = 202

    async def after_restart(http: httpx.AsyncClient) -> None:
        await TelemetryPublisher(http, db_path, "ship-01", 5, clock=lambda: T0).step()

    run_steps(ground, db_path, after_restart)
    failed, sent = ground.batches
    assert sent["batch_id"] != failed["batch_id"]  # ground dedups by update id, not batch id
    assert [u["incident_id"] for u in sent["incident_updates"]] == [incident_id]
    assert incident(db_path, incident_id).ground_delivery == "delivered"


def test_offline_ack_follows_created_with_original_time(
    client: TestClient, astronaut: str, db_path: Path
) -> None:
    incident_id = urgent_incident(client, db_path)["incident"]["id"]
    ack_at = T0 + timedelta(minutes=2)
    ground = FakeGround()
    ground.cursor = 0

    async def scenario(http: httpx.AsyncClient) -> None:
        pub = TelemetryPublisher(http, db_path, "ship-01", 5, clock=lambda: T0 + timedelta(minutes=30))
        ground.status = 503
        with pytest.raises(httpx.HTTPStatusError):
            await pub.step()  # pending batch holds only `created`
        conn = connect(db_path)
        IncidentRepository(conn)._add_event(incident_id, "acknowledged", to_db_timestamp(ack_at), "ana")
        conn.close()
        ground.status = 202
        await pub.step()  # resends the pending batch unchanged: ack not marked
        assert [e.delivered_at is None for e in incident(db_path, incident_id).events] == [False, True]
        await pub.step()

    run_steps(ground, db_path, scenario)
    failed, first, second = ground.batches
    assert failed == first  # same pending batch resent unchanged
    assert [u["type"] for u in first["incident_updates"]] == ["created"]
    [ack] = second["incident_updates"]
    assert (ack["type"], ack["acknowledged_by"]) == ("acknowledged", "ana")
    assert ack["occurred_at"] == "2026-11-14T12:02:00Z"
    assert incident(db_path, incident_id).ground_delivery == "delivered"
