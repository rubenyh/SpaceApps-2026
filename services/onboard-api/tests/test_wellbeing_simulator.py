from datetime import UTC, datetime, timedelta

from wellbeing_support import TODAY

from onboard_api.wellbeing.database import connect_wellbeing
from onboard_api.wellbeing.engine import build_daily_inputs, evaluate
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.schemas import VisionSessionCreate
from onboard_api.wellbeing.settings import WellbeingSettings
from onboard_api.wellbeing.simulator import (
    CREW,
    DERAIL_DAY,
    DISCREPANCY_DAY,
    simulate,
)

SETTINGS = WellbeingSettings()


def evaluate_all(repo: WellbeingRepository):
    results = {}
    for aid in CREW:
        inputs = build_daily_inputs(
            aid,
            repo.list_checkins(aid),
            repo.list_signals(aid),
            repo.list_vision_sessions(aid),
            repo.list_co_presence(aid),
            [],
            SETTINGS,
        )
        results[aid] = evaluate(inputs, TODAY, SETTINGS)
    return results


def test_simulated_crew_tells_the_demo_story(tmp_path) -> None:
    conn = connect_wellbeing(tmp_path / "wellbeing.db")
    repo = WellbeingRepository(conn)
    for seed in range(20):  # the story must not depend on one lucky seed
        simulate(repo, TODAY, seed=seed)
        r = evaluate_all(repo)
        assert r["ast-01"].level == "ok", seed
        assert r["ast-04"].level == "ok", seed  # one bad day never alerts
        assert r["ast-02"].level == "needs_support", seed
        assert r["ast-02"].onset_date == TODAY - timedelta(days=20 - DERAIL_DAY), seed
        assert "vision" in r["ast-02"].sustained_sources, seed
        assert r["ast-03"].discrepancy is True, seed
        assert r["ast-03"].onset_date == TODAY - timedelta(days=20 - DISCREPANCY_DAY), seed
        assert r["ast-03"].sustained_sources == ["vision", "physiology", "social"], seed
        for aid, ev in r.items():  # no gap: activation has data for everyone
            activation = next(i for i in ev.indicators if i.kind == "activation")
            assert activation.status in ("ok", "attention"), (seed, aid, activation.status)
            assert activation.latest_day == TODAY - timedelta(days=1), (seed, aid)
            assert all(i.status != "no_data" for i in ev.indicators), (seed, aid)

    simulate(repo, TODAY)  # rerun replaces, never duplicates
    assert len(repo.list_checkins("ast-01")) == 21
    assert len(repo.list_signals("ast-01")) == 21 * 3
    vision = repo.list_vision_sessions("ast-01")
    assert all(v.simulated for v in vision)
    assert max(v.started_at.date() for v in vision) == TODAY - timedelta(days=1)
    kinds = [v.session_type for v in vision]
    assert kinds.count("bitacora") == 20 and kinds.count("ambiente") == 20 * 3
    assert all(v.motion and v.fatigue is None for v in vision if v.session_type == "ambiente")
    conn.close()


def test_live_log_today_meets_a_formed_baseline(tmp_path) -> None:
    conn = connect_wellbeing(tmp_path / "wellbeing.db")
    repo = WellbeingRepository(conn)
    simulate(repo, TODAY)
    start = datetime.combine(TODAY, datetime.min.time(), tzinfo=UTC).replace(hour=9)
    repo.create_vision_session(
        VisionSessionCreate(
            astronaut_id="ast-01", session_type="bitacora", module_id="modulo-a",
            source="vision:cam0", started_at=start, ended_at=start + timedelta(seconds=90),
            quality="good", valid_frame_ratio=0.94, identity={"method": "face"},
            neutral_ok=True,
            fatigue={"blink_rate_per_min": 18.2, "perclos": 0.07,
                     "eye_openness_vs_neutral": 0.88, "yawn_count": 1, "nod_count": 0},
            tension={"brow_lower_delta": 0.12, "lip_press_delta": 0.05},
        ),
        received_at=start,
    )
    ev = evaluate_all(repo)["ast-01"]
    conn.close()
    fatigue = next(i for i in ev.indicators if i.kind == "fatigue")
    perclos = next(c for c in fatigue.components if c.definition.component == "vision.perclos")
    assert perclos.ready and perclos.latest_day == TODAY and perclos.latest_z is not None
    assert fatigue.status != "baseline_pending"


def test_perclos_range_is_configurable(tmp_path) -> None:
    import pytest

    conn = connect_wellbeing(tmp_path / "wellbeing.db")
    repo = WellbeingRepository(conn)
    simulate(repo, TODAY, perclos=(0.03, 0.06))
    values = [v.fatigue.perclos for v in repo.list_vision_sessions("ast-01") if v.fatigue]
    assert all(0.03 <= p <= 0.06 for p in values)
    altered = [v.fatigue.perclos for v in repo.list_vision_sessions("ast-02") if v.fatigue][-3:]
    assert all(0.16 <= p <= 0.26 for p in altered)
    with pytest.raises(ValueError):
        simulate(repo, TODAY, perclos=(0.2, 0.1))
    conn.close()
