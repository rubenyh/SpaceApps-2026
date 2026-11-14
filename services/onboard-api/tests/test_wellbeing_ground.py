import sqlite3
from datetime import timedelta
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient
from wellbeing_support import (  # noqa: F401 (fixtures)
    TODAY,
    checkin_body,
    wb_client,
    wb_clock,
    wb_settings,
)

from onboard_api.wellbeing.database import SCHEMA_VERSION, connect_wellbeing


def package(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "astronaut_id": "ast-01",
        "requested_by": "self",
        "requested_by_name": "X",
        "consent": {"astronaut_confirmed": True, "statement_version": "v1"},
        "period_from": (TODAY - timedelta(days=2)).isoformat(),
        "period_to": TODAY.isoformat(),
        "include": ["assessment", "timeline", "checkins"],
        "note": None,
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize("requester", ["self", "captain", "ground_psychologist"])
def test_package_is_queued_with_consent(wb_client: TestClient, requester: str) -> None:
    response = wb_client.post("/wellbeing/ground-packages", json=package(requested_by=requester))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued" and body["requested_by"] == requester
    assert body["consent_statement_version"] == "v1"
    assert "consent" not in body
    listed = wb_client.get("/wellbeing/ground-packages?astronaut_id=ast-01").json()
    assert [p["id"] for p in listed] == [body["id"]]


@pytest.mark.parametrize(
    "overrides",
    [
        {"consent": {"astronaut_confirmed": False, "statement_version": "v1"}},
        {"consent": None},
        {"include": ["comments"]},
        {"include": []},
        {"period_from": TODAY.isoformat(), "period_to": (TODAY - timedelta(days=1)).isoformat()},
        {"period_to": (TODAY + timedelta(days=1)).isoformat()},
        {"requested_by": "anyone"},
    ],
)
def test_invalid_package_is_422(wb_client: TestClient, overrides: dict[str, object]) -> None:
    response = wb_client.post("/wellbeing/ground-packages", json=package(**overrides))
    assert response.status_code == 422
    assert wb_client.get("/wellbeing/ground-packages?astronaut_id=ast-01").json() == []


def test_unknown_astronaut_is_404(wb_client: TestClient) -> None:
    for aid in ("ast-09", "unknown-4"):
        assert wb_client.post(
            "/wellbeing/ground-packages", json=package(astronaut_id=aid)
        ).status_code == 404


def test_content_hides_comments_unless_included(wb_client: TestClient) -> None:
    for i in range(3):
        day = (TODAY - timedelta(days=i)).isoformat()
        wb_client.put(
            f"/astronauts/ast-01/wellbeing/checkins/{day}",
            json=checkin_body(comment="privado"),
        )
    plain = wb_client.post("/wellbeing/ground-packages", json=package()).json()
    content = wb_client.get(f"/wellbeing/ground-packages/{plain['id']}/content").json()
    assert len(content["checkins"]) == 3
    assert all(c["comment"] is None for c in content["checkins"])
    assert len(content["timeline"]["days"]) == 3
    assert content["assessment"]["astronaut_id"] == "ast-01"

    with_comments = wb_client.post(
        "/wellbeing/ground-packages",
        json=package(include=["checkins", "comments"]),
    ).json()
    content = wb_client.get(f"/wellbeing/ground-packages/{with_comments['id']}/content").json()
    assert {c["comment"] for c in content["checkins"]} == {"privado"}
    assert content["assessment"] is None and content["timeline"] is None


def test_withdraw_blocks_content(wb_client: TestClient) -> None:
    created = wb_client.post("/wellbeing/ground-packages", json=package()).json()
    url = f"/wellbeing/ground-packages/{created['id']}"
    first = wb_client.post(f"{url}/withdraw")
    assert first.status_code == 200 and first.json()["status"] == "withdrawn"
    assert wb_client.post(f"{url}/withdraw").json()["status"] == "withdrawn"
    assert wb_client.get(f"{url}/content").status_code == 409
    assert wb_client.post("/wellbeing/ground-packages/nope/withdraw").status_code == 404


def test_v1_database_migrates_and_keeps_data(tmp_path) -> None:
    path = tmp_path / "wellbeing.db"
    conn = sqlite3.connect(path)
    v1 = files("onboard_api.wellbeing").joinpath("schema.sql").read_text("utf-8")
    conn.executescript(v1)
    conn.execute(
        "INSERT INTO signals (astronaut_id, kind, value, unit, recorded_at, received_at,"
        " quality, source) VALUES ('ast-01', 'hrv_sdnn', 50, 'ms', 'x', 'x', 'good', 't')"
    )
    conn.commit()
    conn.close()

    migrated = connect_wellbeing(path)
    assert migrated.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 2
    assert migrated.execute("SELECT count(*) FROM signals").fetchone()[0] == 1
    assert migrated.execute("SELECT count(*) FROM ground_packages").fetchone()[0] == 0
    migrated.close()
