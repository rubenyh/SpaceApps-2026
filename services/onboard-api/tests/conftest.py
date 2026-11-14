from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onboard_api.config import Settings
from onboard_api.dependencies import get_clock
from onboard_api.main import create_app

T0 = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    # Nested directory checks that startup creates the parent directory.
    return tmp_path / "nested" / "onboard.db"


@pytest.fixture
def make_client(
    db_path: Path, clock: FakeClock
) -> Iterator[Callable[[], TestClient]]:
    """Factory of clients, each a fresh app instance on the same DB file."""
    clients: list[TestClient] = []

    def factory() -> TestClient:
        app = create_app(Settings(db_path=db_path))
        app.dependency_overrides[get_clock] = lambda: clock
        client = TestClient(app)
        client.__enter__()  # run lifespan
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[[], TestClient]) -> TestClient:
    return make_client()


@pytest.fixture
def astronaut(client: TestClient) -> str:
    response = client.post("/astronauts", json={"id": "ana", "display_name": "Ana"})
    assert response.status_code == 201
    return "ana"


def reading_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "astronaut_id": "ana",
        "kind": "heart_rate",
        "value": 72,
        "unit": "bpm",
        "recorded_at": "2026-11-14T11:59:00Z",
        "quality": "good",
        "source": "manual",
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}
