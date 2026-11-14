from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from wellbeing_support import (  # noqa: F401 (fixtures)
    NOW,
    TODAY,
    checkin_body,
    insert_heart_rates,
    wb_client,
    wb_clock,
    wb_settings,
)

from onboard_api.wellbeing.settings import WellbeingSettings

VISION = {
    "astronaut_id": "ast-01",
    "session_type": "bitacora",
    "module_id": "modulo-a",
    "source": "vision:cam0",
    "started_at": "2026-11-14T08:00:00Z",
    "ended_at": "2026-11-14T08:01:30Z",
    "quality": "good",
    "valid_frame_ratio": 0.94,
    "identity": {"method": "face", "match_score": 0.71},
    "neutral_ok": True,
    "fatigue": {"blink_rate_per_min": 18.2, "perclos": 0.07,
                "eye_openness_vs_neutral": 0.88, "yawn_count": 1, "nod_count": 0},
    "tension": {"brow_lower_delta": 0.12, "lip_press_delta": 0.05},
    "motion": None,
    "provisional": True,
}

CO_PRESENCE = {
    "module_id": "modulo-a",
    "source": "vision:cam0",
    "window_start": "2026-11-14T12:00:00Z",
    "window_end": "2026-11-14T12:01:00Z",
    "occupants": [{"astronaut_id": "ast-01", "seconds_present": 58},
                  {"astronaut_id": "unknown-3", "seconds_present": 30}],
    "pairs": [{"a": "ast-01", "b": "unknown-3", "seconds_together": 25,
               "mean_distance_shoulders": 2.3, "facing_ratio": 0.4}],
    "provisional": True,
}


def put_checkin(client: TestClient, day, astronaut: str = "ast-01", **overrides):
    return client.put(
        f"/astronauts/{astronaut}/wellbeing/checkins/{day.isoformat()}",
        json=checkin_body(**overrides),
    )


def test_checkin_upsert_replaces_same_day(wb_client: TestClient) -> None:
    first = put_checkin(wb_client, TODAY, mood=2)
    assert first.status_code == 200
    assert first.json()["simulated"] is False
    second = put_checkin(wb_client, TODAY, mood=4, comment="todo bien", source="simulated")
    assert second.json()["mood"] == 4 and second.json()["simulated"] is True
    listed = wb_client.get("/astronauts/ast-01/wellbeing/checkins").json()
    assert len(listed) == 1 and listed[0]["comment"] == "todo bien"


def test_checkin_errors(wb_client: TestClient) -> None:
    assert put_checkin(wb_client, TODAY, astronaut="nobody").status_code == 404
    assert put_checkin(wb_client, TODAY + timedelta(days=1)).status_code == 422
    assert put_checkin(wb_client, TODAY, mood=5).status_code == 422
    assert put_checkin(wb_client, TODAY, sleep_hours=7.3).status_code == 422


def test_signal_unit_must_match_kind(wb_client: TestClient) -> None:
    body = {"astronaut_id": "ast-01", "kind": "hrv_sdnn", "value": 48.2, "unit": "ms",
            "recorded_at": "2026-11-14T07:10:00Z", "quality": "good",
            "source": "apple_watch_export"}
    ok = wb_client.post("/wellbeing/signals", json=body)
    assert ok.status_code == 201 and ok.json()["id"] >= 1
    assert wb_client.post("/wellbeing/signals", json={**body, "unit": "s"}).status_code == 422


def test_vision_session_round_trip_and_unknown_person(wb_client: TestClient) -> None:
    created = wb_client.post("/wellbeing/vision-sessions", json=VISION)
    assert created.status_code == 201
    assert created.json()["fatigue"]["perclos"] == 0.07
    unknown = wb_client.post(
        "/wellbeing/vision-sessions", json={**VISION, "astronaut_id": "unknown-12"}
    )
    assert unknown.status_code == 201
    missing = wb_client.post("/wellbeing/vision-sessions", json={**VISION, "astronaut_id": "ast-09"})
    assert missing.status_code == 404
    empty = {**VISION, "fatigue": None, "tension": None}
    assert wb_client.post("/wellbeing/vision-sessions", json=empty).status_code == 422


def test_co_presence_validation(wb_client: TestClient) -> None:
    assert wb_client.post("/wellbeing/co-presence", json=CO_PRESENCE).status_code == 201
    bad_pair = {**CO_PRESENCE, "pairs": [{"a": "ast-01", "b": "ast-02", "seconds_together": 5}]}
    assert wb_client.post("/wellbeing/co-presence", json=bad_pair).status_code == 422
    too_long = {**CO_PRESENCE, "occupants": [{"astronaut_id": "ast-01", "seconds_present": 61}],
                "pairs": []}
    assert wb_client.post("/wellbeing/co-presence", json=too_long).status_code == 422
    stranger = {**CO_PRESENCE, "occupants": [{"astronaut_id": "ast-09", "seconds_present": 5}],
                "pairs": []}
    assert wb_client.post("/wellbeing/co-presence", json=stranger).status_code == 404


def test_assessment_timeline_and_crew_after_a_derailment(wb_client: TestClient) -> None:
    for i in range(14):
        day = TODAY - timedelta(days=13 - i)
        derailed = i >= 9  # last 5 days
        put_checkin(
            wb_client, day, mood=1 if derailed else 3, stress=4 if derailed else 1,
            source="simulated",
        )

    assessment = wb_client.get("/astronauts/ast-01/wellbeing").json()
    assert assessment["level"] == "attention"
    assert assessment["sustained_sources"] == ["checkin"]
    assert assessment["onset_date"] == (TODAY - timedelta(days=4)).isoformat()
    assert [i["kind"] for i in assessment["indicators"]] == [
        "sleep", "fatigue", "stress", "activation", "social", "mood"
    ]
    assert (assessment["simulated_days"], assessment["live_days"], assessment["mixed_days"]) == (14, 0, 0)
    assert assessment["latest_origin"] == "simulated"
    assert assessment["provisional"] is True
    assert "Días con datos: 0 en vivo, 14 simulados, 0 mixtos (en vivo + simulados)." in assessment["data_notices"]

    timeline = wb_client.get("/astronauts/ast-01/wellbeing/timeline?days=14").json()
    levels = [d["level"] for d in timeline["days"]]
    assert len(levels) == 14
    # Sustained only after 3 altered days, never retroactively.
    assert levels[-5:] == ["ok", "ok", "attention", "attention", "attention"]
    assert timeline["onset_date"] == assessment["onset_date"]

    crew = wb_client.get("/wellbeing/crew").json()
    members = {m["astronaut_id"]: m for m in crew["members"]}
    assert set(members) == {"ast-01", "ast-02", "ast-03"}
    assert members["ast-01"]["level"] == "attention" and members["ast-01"]["latest_origin"] == "simulated"
    assert members["ast-02"]["level"] == "no_data"
    # Crew view carries no detail.
    assert set(members["ast-01"]) == {"astronaut_id", "display_name", "level", "trend", "latest_origin"}


def test_onboard_heart_rate_is_read_only_input(
    wb_client: TestClient, wb_settings: WellbeingSettings
) -> None:
    at = NOW.replace(hour=6)
    insert_heart_rates(
        wb_settings.onboard_db_path, "ast-02",
        [(at + timedelta(minutes=i), 60 + i, "good") for i in range(10)]
        + [(at, 40, "suspect")],
    )
    body = wb_client.get("/astronauts/ast-02/wellbeing").json()
    stress = next(i for i in body["indicators"] if i["kind"] == "stress")
    hr = next(c for c in stress["components"] if c["component"] == "onboard.heart_rate_low")
    assert hr["latest_value"] == 60
    assert any("calidad dudosa" in n for n in body["data_notices"])


def test_missing_onboard_db_is_503_and_not_created(
    wb_client: TestClient, wb_settings: WellbeingSettings, tmp_path: Path
) -> None:
    wb_settings.onboard_db_path = tmp_path / "missing" / "onboard.db"
    assert wb_client.get("/wellbeing/crew").status_code == 503
    assert not wb_settings.onboard_db_path.exists()


def test_parameters_and_form(wb_client: TestClient) -> None:
    params = wb_client.get("/wellbeing/parameters").json()
    assert params["provisional"] is True and params["z_threshold"] == 1.5
    assert {c["component"] for c in params["components"]} >= {"checkin.mood", "vision.perclos"}
    form = wb_client.get("/wellbeing/checkin-form").json()
    assert [i["key"] for i in form["items"]][-1] == "comment"


def test_numeric_series_filters_unit_and_text_values(wb_settings: WellbeingSettings) -> None:
    from onboard_api.repositories.database import connect
    from onboard_api.repositories.readings import ReadingRepository

    at = NOW.replace(hour=6)
    insert_heart_rates(wb_settings.onboard_db_path, "ast-01", [(at, 70, "good")])
    conn = connect(wb_settings.onboard_db_path)
    conn.execute(
        "INSERT INTO readings (astronaut_id, kind, value, value_text, unit, recorded_at,"
        " received_at, quality, source) VALUES"
        " ('ast-01', 'heart_rate', 71, NULL, 'beats/min', ?, ?, 'good', 't'),"
        " ('ast-01', 'heart_rate', NULL, 'n/a', 'bpm', ?, ?, 'good', 't')",
        ["2026-11-14T05:00:00.000000Z"] * 4,
    )
    series = ReadingRepository(conn).numeric_series("ast-01", "heart_rate", "bpm")
    conn.close()
    assert [r.value for r in series] == [70]


def test_live_log_on_a_simulated_day_is_marked_live_and_mixed(wb_client: TestClient) -> None:
    for i in range(8):
        day = TODAY - timedelta(days=7 - i)
        put_checkin(wb_client, day, source="simulated")
    live = {**VISION, "started_at": NOW.replace(hour=9).isoformat(),
            "ended_at": NOW.replace(hour=9, minute=1).isoformat()}
    assert wb_client.post("/wellbeing/vision-sessions", json=live).status_code == 201

    body = wb_client.get("/astronauts/ast-01/wellbeing").json()
    assert (body["live_days"], body["simulated_days"], body["mixed_days"]) == (0, 7, 1)
    assert body["latest_origin"] == "mixed"
    fatigue = next(i for i in body["indicators"] if i["kind"] == "fatigue")
    origins = {c["component"]: c["latest_origin"] for c in fatigue["components"]}
    assert origins["vision.perclos"] == "live"
    assert origins["checkin.energy"] == "simulated"
    assert fatigue["latest_origin"] == "mixed"

    days = wb_client.get("/astronauts/ast-01/wellbeing/timeline?days=9").json()["days"]
    assert [d["origin"] for d in days] == [None] + ["simulated"] * 7 + ["mixed"]
    crew = {m["astronaut_id"]: m for m in wb_client.get("/wellbeing/crew").json()["members"]}
    assert crew["ast-01"]["latest_origin"] == "mixed"
