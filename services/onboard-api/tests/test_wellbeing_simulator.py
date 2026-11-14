from datetime import timedelta

from wellbeing_support import TODAY

from onboard_api.wellbeing.database import connect_wellbeing
from onboard_api.wellbeing.engine import build_daily_inputs, evaluate
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.settings import WellbeingSettings
from onboard_api.wellbeing.simulator import CREW, DERAIL_DAY, simulate

SETTINGS = WellbeingSettings()


def test_simulated_crew_tells_the_demo_story(tmp_path) -> None:
    conn = connect_wellbeing(tmp_path / "wellbeing.db")
    repo = WellbeingRepository(conn)
    simulate(repo, TODAY)
    simulate(repo, TODAY)  # rerun replaces, never duplicates
    results = {}
    for aid in CREW:
        inputs = build_daily_inputs(
            aid,
            repo.list_checkins(aid),
            repo.list_signals(aid),
            [],
            repo.list_co_presence(aid),
            [],
            SETTINGS,
        )
        results[aid] = evaluate(inputs, TODAY, SETTINGS)
    assert len(repo.list_checkins("ast-01")) == 21
    assert len(repo.list_signals("ast-01")) == 21 * 3
    conn.close()

    assert results["ast-01"].level == "ok"
    assert results["ast-04"].level == "ok"  # one bad day never alerts
    assert results["ast-02"].level == "needs_support"
    assert results["ast-02"].onset_date == TODAY - timedelta(days=20 - DERAIL_DAY)
    assert results["ast-03"].discrepancy is True
    assert results["ast-03"].level == "needs_support"
