from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from wellbeing_support import (  # noqa: F401 (fixtures)
    checkin_body,
    wb_client,
    wb_clock,
    wb_settings,
)

from onboard_api.wellbeing.database import connect_wellbeing
from onboard_api.wellbeing.engine import build_daily_inputs, evaluate
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.schemas import Signal
from onboard_api.wellbeing.settings import WellbeingSettings
from onboard_api.wellbeing.simulator import CREW, DERAIL_DAY, DISCREPANCY_DAY, simulate

TIJUANA = ZoneInfo("America/Tijuana")
# 17:00 in Tijuana on 2026-11-10 is 01:00 UTC on 2026-11-11.
AT_17_LOCAL = datetime(2026, 11, 10, 17, 0, tzinfo=TIJUANA)


def hrv_at(moment: datetime) -> Signal:
    return Signal(id=1, astronaut_id="ast-01", kind="hrv_sdnn", value=50, unit="ms",
                  recorded_at=moment, received_at=moment, quality="good",
                  source="apple_watch_export", simulated=False)


def test_17h_tijuana_falls_on_the_local_day_only_with_mission_tz() -> None:
    local = WellbeingSettings(mission_tz="America/Tijuana")
    inputs = build_daily_inputs("ast-01", [], [hrv_at(AT_17_LOCAL)], [], [], [], local)
    assert set(inputs.values["signal.hrv_sdnn"]) == {date(2026, 11, 10)}

    default = WellbeingSettings()
    assert default.mission_tz == "UTC"
    inputs = build_daily_inputs("ast-01", [], [hrv_at(AT_17_LOCAL)], [], [], [], default)
    assert set(inputs.values["signal.hrv_sdnn"]) == {date(2026, 11, 11)}


def test_unknown_zone_is_rejected() -> None:
    with pytest.raises(ValueError):
        WellbeingSettings(mission_tz="Mars/Olympus")


def test_api_uses_the_mission_day(wb_client: TestClient, wb_settings, wb_clock) -> None:
    wb_settings.mission_tz = "America/Tijuana"
    wb_clock.now = AT_17_LOCAL.astimezone(UTC)  # 2026-11-11T01:00Z, still the 10th locally
    assert wb_client.get("/wellbeing/parameters").json()["mission_tz"] == "America/Tijuana"
    # The 11th is "tomorrow" in Tijuana, so a check-in for it is in the future.
    assert wb_client.put("/astronauts/ast-01/wellbeing/checkins/2026-11-11",
                         json=checkin_body()).status_code == 422
    assert wb_client.put("/astronauts/ast-01/wellbeing/checkins/2026-11-10",
                         json=checkin_body()).status_code == 200
    body = {"astronaut_id": "ast-01", "kind": "hrv_sdnn", "value": 50, "unit": "ms",
            "recorded_at": wb_clock.now.isoformat(), "quality": "good", "source": "watch"}
    assert wb_client.post("/wellbeing/signals", json=body).status_code == 201
    assessment = wb_client.get("/astronauts/ast-01/wellbeing").json()
    assert assessment["latest_day"] == "2026-11-10"
    days = wb_client.get("/astronauts/ast-01/wellbeing/timeline?days=2").json()["days"]
    assert [d["day"] for d in days] == ["2026-11-09", "2026-11-10"]


def test_simulator_story_holds_in_tijuana(tmp_path) -> None:
    local = WellbeingSettings(mission_tz="America/Tijuana")
    today = date(2026, 11, 15)
    conn = connect_wellbeing(tmp_path / "wellbeing.db")
    repo = WellbeingRepository(conn)
    simulate(repo, today, tz=local.tz)
    ev = {}
    for aid in CREW:
        signals = repo.list_signals(aid)
        assert {local.day_of(s.recorded_at) for s in signals} == {
            today - timedelta(days=i) for i in range(21)
        }
        vision = repo.list_vision_sessions(aid)
        assert max(local.day_of(v.started_at) for v in vision) == today - timedelta(days=1)
        inputs = build_daily_inputs(aid, repo.list_checkins(aid), signals, vision,
                                    repo.list_co_presence(aid), [], local)
        ev[aid] = evaluate(inputs, today, local)
    conn.close()
    assert ev["ast-01"].level == "ok" and ev["ast-04"].level == "ok"
    assert ev["ast-02"].onset_date == today - timedelta(days=20 - DERAIL_DAY)
    assert ev["ast-03"].discrepancy
    assert ev["ast-03"].onset_date == today - timedelta(days=20 - DISCREPANCY_DAY)
