import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

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
    assert _keys(batch.model_dump(mode="json")) == _keys(raw)


class FakeGround:
    def __init__(self) -> None:
        self.up = True
        self.batches: list[dict] = []
        self.cursor: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("link down", request=request)
        if request.url.path == "/telemetry/v1/cursor":
            return httpx.Response(200, json={"last_reading_id": self.cursor})
        self.batches.append(json.loads(request.content))
        return httpx.Response(202, json={"accepted": 0, "duplicates": 0})


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
