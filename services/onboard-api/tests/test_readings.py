from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from conftest import reading_payload


def test_create_reading(client: TestClient, astronaut: str) -> None:
    response = client.post(
        "/readings", json=reading_payload(recorded_at="2026-11-14T13:59:00+02:00")
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] >= 1
    assert body["value"] == 72
    assert body["value_text"] is None
    # Stored and returned in UTC.
    assert body["recorded_at"] == "2026-11-14T11:59:00Z"
    assert body["received_at"] == "2026-11-14T12:00:00Z"


def test_text_reading_and_sensor_without_unit(client: TestClient, astronaut: str) -> None:
    color = client.post(
        "/readings",
        json=reading_payload(kind="urine_color", value=None, value_text="#E0C060", unit="rgb_hex"),
    )
    assert color.status_code == 201
    # muscle_density has no configured unit: any unit is accepted.
    density = client.post(
        "/readings", json=reading_payload(kind="muscle_density", value=1.1, unit="g/cm3")
    )
    assert density.status_code == 201


def test_unknown_astronaut_is_404(client: TestClient) -> None:
    response = client.post("/readings", json=reading_payload(astronaut_id="nobody"))
    assert response.status_code == 404
    assert response.json() == {"detail": "Astronaut 'nobody' not found"}


def test_unit_mismatch_is_422(client: TestClient, astronaut: str) -> None:
    response = client.post("/readings", json=reading_payload(unit="beats/min"))
    assert response.status_code == 422
    assert "configured unit 'bpm'" in response.json()["detail"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"recorded_at": "2026-11-14T11:59:00"},  # naive datetime
        {"value_text": "72"},  # both value and value_text
        {"value": None},  # neither
        {"kind": "blood_sugar"},
        {"quality": "excellent"},
    ],
)
def test_invalid_reading_is_422(
    client: TestClient, astronaut: str, overrides: dict[str, object]
) -> None:
    payload = reading_payload()
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}
    assert client.post("/readings", json=payload).status_code == 422


def _seed(client: TestClient) -> None:
    for minute, kind, value, unit in [
        (10, "heart_rate", 70, "bpm"),
        (30, "heart_rate", 75, "bpm"),
        (20, "spo2", 98, "%"),
        (40, "heart_rate", 80, "bpm"),
    ]:
        response = client.post(
            "/readings",
            json=reading_payload(
                kind=kind, value=value, unit=unit, recorded_at=f"2026-11-14T11:{minute}:00Z"
            ),
        )
        assert response.status_code == 201


def test_list_readings_order_filter_limit(client: TestClient, astronaut: str) -> None:
    _seed(client)
    get = lambda **params: client.get("/readings", params={"astronaut_id": "ana", **params})

    all_readings = get().json()
    assert [r["recorded_at"][11:16] for r in all_readings] == ["11:40", "11:30", "11:20", "11:10"]

    assert [r["value"] for r in get(kind="heart_rate").json()] == [80, 75, 70]
    assert [r["value"] for r in get(kind="spo2").json()] == [98]
    assert [r["value"] for r in get(limit=2).json()] == [80, 75]

    # since/until are inclusive and compared in UTC.
    window = get(since="2026-11-14T13:20:00+02:00", until="2026-11-14T11:30:00Z").json()
    assert [r["value"] for r in window] == [75, 98]


def test_list_readings_empty_and_errors(client: TestClient, astronaut: str) -> None:
    response = client.get("/readings", params={"astronaut_id": "ana"})
    assert response.status_code == 200
    assert response.json() == []

    assert client.get("/readings", params={"astronaut_id": "nobody"}).status_code == 404
    assert client.get("/readings").status_code == 422
    for bad in [
        {"limit": 0},
        {"limit": 1001},
        {"since": "2026-11-14T11:00:00"},
        {"kind": "blood_sugar"},
    ]:
        response = client.get("/readings", params={"astronaut_id": "ana", **bad})
        assert response.status_code == 422, bad


def test_persistence_across_app_instances(
    make_client: Callable[[], TestClient], db_path
) -> None:
    first = make_client()
    first.post("/astronauts", json={"id": "ana", "display_name": "Ana"})
    first.post("/readings", json=reading_payload())
    first.put(
        "/sensors/spo2",
        json={
            "unit": "%",
            "stale_after_seconds": 600,
            "normal_min": 92,
            "normal_max": 100,
            "range_role": "health",
            "provisional": True,
            "range_source": "test",
        },
    )

    second = make_client()
    assert [a["id"] for a in second.get("/astronauts").json()] == ["ana"]
    assert len(second.get("/readings", params={"astronaut_id": "ana"}).json()) == 1
    assert second.get("/sensors").json()[1]["normal_min"] == 92
