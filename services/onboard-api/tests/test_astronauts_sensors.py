from typing import get_args

from fastapi.testclient import TestClient

from onboard_api.schemas.sensors import SensorKind


def test_health(client: TestClient) -> None:
    assert client.get("/").json() == {"status": "ok"}


def test_create_and_list_astronauts(client: TestClient) -> None:
    assert client.get("/astronauts").json() == []
    response = client.post("/astronauts", json={"id": "zoe", "display_name": "Zoe"})
    assert response.status_code == 201
    assert response.json() == {
        "id": "zoe",
        "display_name": "Zoe",
        "created_at": "2026-11-14T12:00:00Z",
    }
    client.post("/astronauts", json={"id": "ana", "display_name": "Ana"})
    assert [a["id"] for a in client.get("/astronauts").json()] == ["ana", "zoe"]


def test_duplicate_astronaut_is_409(client: TestClient, astronaut: str) -> None:
    response = client.post("/astronauts", json={"id": astronaut, "display_name": "Other"})
    assert response.status_code == 409
    assert response.json() == {"detail": "Astronaut 'ana' already exists"}


def test_invalid_astronaut_id_is_422(client: TestClient) -> None:
    response = client.post("/astronauts", json={"id": "Ana!", "display_name": "Ana"})
    assert response.status_code == 422


def test_sensors_seeded_in_kind_order(client: TestClient) -> None:
    sensors = client.get("/sensors").json()
    assert [s["kind"] for s in sensors] == list(get_args(SensorKind))
    assert all(s["provisional"] is True for s in sensors)
    heart_rate = sensors[0]
    assert heart_rate == {
        "kind": "heart_rate",
        "unit": "bpm",
        "stale_after_seconds": 300,
        "normal_min": 60.0,
        "normal_max": 100.0,
        "range_role": "health",
        "provisional": True,
        "range_source": "AHA / Mayo Clinic",
    }
    by_kind = {s["kind"]: s for s in sensors}
    assert by_kind["urine_temperature"]["unit"] == "°C"
    assert by_kind["urine_temperature"]["range_role"] == "sample_validity"
    assert by_kind["muscle_density"]["unit"] is None


def _update_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "unit": "bpm",
        "stale_after_seconds": 300,
        "normal_min": 60,
        "normal_max": 100,
        "range_role": "health",
        "provisional": False,
        "range_source": "test",
    }
    body.update(overrides)
    return body


def test_put_sensor(client: TestClient) -> None:
    response = client.put("/sensors/heart_rate", json=_update_body(normal_max=90))
    assert response.status_code == 200
    assert response.json()["normal_max"] == 90
    assert response.json()["provisional"] is False
    assert client.get("/sensors").json()[0]["normal_max"] == 90


def test_put_unknown_sensor_is_404(client: TestClient) -> None:
    response = client.put("/sensors/blood_sugar", json=_update_body())
    assert response.status_code == 404
    assert "detail" in response.json()


def test_put_sensor_invalid_body_is_422(client: TestClient) -> None:
    response = client.put("/sensors/heart_rate", json=_update_body(normal_min=120))
    assert response.status_code == 422
