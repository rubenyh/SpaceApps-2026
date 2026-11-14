from datetime import UTC, datetime, timedelta

from wellbeing_support import TODAY, series_inputs

from onboard_api.wellbeing.engine import build_daily_inputs, evaluate, support_notes
from onboard_api.schemas.readings import Reading
from onboard_api.wellbeing.schemas import CoPresence, Signal, VisionSession
from onboard_api.wellbeing.settings import WellbeingSettings

SETTINGS = WellbeingSettings()
DAYS = 21
START = TODAY - timedelta(days=DAYS - 1)
DERAIL = 14  # index of the first altered day


def day(i: int):
    return START + timedelta(days=i)


def mood(i: int) -> float:
    return 1.0 if i >= DERAIL else (4.0 if i % 3 == 2 else 3.0)


def stable_mood(i: int) -> float:
    return 4.0 if i % 3 == 2 else 3.0


def hrv(i: int) -> float:
    return 38.0 if i >= DERAIL else [50, 52, 48, 50, 51, 49, 50][i % 7]


def social(i: int) -> float:
    return 60.0 if i >= DERAIL else [120, 130, 110, 120, 125, 115, 120][i % 7]


def test_stable_person_is_ok() -> None:
    inputs = series_inputs({"checkin.mood": stable_mood, "signal.hrv_sdnn": lambda i: 50.0}, DAYS)
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "ok"
    assert ev.onset_date is None
    assert ev.sustained_sources == []
    assert ev.discrepancy is False
    # Coverage confidence: two fresh sources with a baseline.
    assert ev.confidence == "medium"


def test_single_source_sustained_change_is_attention_with_onset() -> None:
    inputs = series_inputs({"checkin.mood": mood}, DAYS)
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "attention"
    assert ev.confidence == "low"
    assert ev.sustained_sources == ["checkin"]
    assert ev.onset_date == day(DERAIL)
    assert ev.sustained_days == DAYS - DERAIL
    mood_indicator = next(i for i in ev.indicators if i.kind == "mood")
    assert mood_indicator.status == "attention"
    assert mood_indicator.run is not None and mood_indicator.run.start == day(DERAIL)


def test_two_sources_agreeing_need_support() -> None:
    inputs = series_inputs({"checkin.mood": mood, "signal.hrv_sdnn": hrv}, DAYS)
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "needs_support"
    assert ev.confidence == "medium"
    assert ev.sustained_sources == ["checkin", "physiology"]
    assert ev.discrepancy is False


def test_discrepancy_when_self_report_is_fine_but_passive_signals_drop() -> None:
    inputs = series_inputs(
        {
            "checkin.mood": stable_mood,
            "signal.hrv_sdnn": hrv,
            "social.accompanied_minutes": social,
        },
        DAYS,
    )
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "needs_support"
    assert ev.discrepancy is True
    assert ev.sustained_sources == ["physiology", "social"]
    assert any("checklist no muestra cambios" in n for n in support_notes(ev, SETTINGS))


def test_alert_only_after_sustain_days() -> None:
    inputs = series_inputs({"checkin.mood": mood}, DAYS)
    # Two altered days: not yet sustained.
    assert evaluate(inputs, day(DERAIL + 1), SETTINGS).level == "ok"
    third = evaluate(inputs, day(DERAIL + 2), SETTINGS)
    assert third.level == "attention"
    assert third.onset_date == day(DERAIL)


def test_missing_day_does_not_break_a_run_but_a_normal_day_does() -> None:
    missing = series_inputs(
        {"checkin.mood": lambda i: None if i == DERAIL + 1 else mood(i)}, DAYS
    )
    ev = evaluate(missing, day(DERAIL + 3), SETTINGS)
    assert ev.level == "attention"
    assert ev.onset_date == day(DERAIL)

    normal_gap = series_inputs(
        {"checkin.mood": lambda i: 3.0 if i == DERAIL + 2 else mood(i)}, DAYS
    )
    assert evaluate(normal_gap, day(DERAIL + 4), SETTINGS).level == "ok"


def test_baseline_pending_with_few_days() -> None:
    inputs = series_inputs({"checkin.mood": stable_mood}, 3)
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "baseline_pending"
    assert "faltan 2 día(s)" in support_notes(ev, SETTINGS)[0]


def test_stale_when_latest_data_is_old() -> None:
    inputs = series_inputs({"checkin.mood": stable_mood}, 15, end=TODAY - timedelta(days=5))
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "stale"
    assert ev.trend == "unknown"


def test_no_data() -> None:
    ev = evaluate(series_inputs({}, 0), TODAY, SETTINGS)
    assert ev.level == "no_data"
    assert all(i.status == "no_data" for i in ev.indicators)


def test_trend_worsening_at_the_start_of_a_change() -> None:
    inputs = series_inputs({"checkin.mood": mood}, DAYS)
    assert evaluate(inputs, day(DERAIL + 2), SETTINGS).trend == "worsening"
    # Once the change plateaus, the trend is stable (level stays attention).
    assert evaluate(inputs, TODAY, SETTINGS).trend == "stable"


def test_activation_counts_both_directions() -> None:
    inputs = series_inputs(
        {"vision.speed": lambda i: 0.2 if i >= DERAIL else [1.0, 1.1, 0.9][i % 3]},
        DAYS,
    )
    ev = evaluate(inputs, TODAY, SETTINGS)
    assert ev.level == "attention"
    assert ev.sustained_sources == ["vision"]


def hr(value: float, at: datetime, quality: str = "good") -> Reading:
    return Reading(id=1, astronaut_id="ast-01", kind="heart_rate", value=value, unit="bpm",
                   recorded_at=at, received_at=at, quality=quality, source="serial:pulse")


def test_build_daily_inputs_quality_rates_and_onboard_heart_rate() -> None:
    t = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    common = {"astronaut_id": "ast-01", "received_at": t}
    signals = [
        Signal(id=1, kind="hrv_sdnn", value=50, unit="ms", recorded_at=t, quality="good",
               source="apple_watch_export", simulated=False, **common),
        Signal(id=2, kind="hrv_sdnn", value=10, unit="ms", recorded_at=t, quality="suspect",
               source="apple_watch_export", simulated=False, **common),
        Signal(id=3, kind="hrv_sdnn", value=99, unit="ms", recorded_at=t, quality="bad",
               source="simulated", simulated=True, **common),
    ]
    vision = [
        VisionSession(id=1, astronaut_id="ast-01", session_type="bitacora", module_id="modulo-a",
                      source="vision:cam0", started_at=t, ended_at=t + timedelta(minutes=2),
                      quality="good", valid_frame_ratio=0.9,
                      identity={"method": "face", "match_score": 0.8}, neutral_ok=False,
                      fatigue={"perclos": 0.1, "yawn_count": 2, "eye_openness_vs_neutral": 0.8},
                      tension={"brow_lower_delta": 0.2}, received_at=t, simulated=False),
    ]
    co = [
        CoPresence(id=1, module_id="modulo-a", source="vision:cam0", window_start=t,
                   window_end=t + timedelta(seconds=60),
                   occupants=[{"astronaut_id": a, "seconds_present": 60}
                              for a in ("ast-01", "ast-02", "unknown-7")],
                   pairs=[{"a": "ast-01", "b": "ast-02", "seconds_together": 30},
                          {"a": "ast-01", "b": "unknown-7", "seconds_together": 45}],
                   received_at=t, simulated=False),
        CoPresence(id=2, module_id="modulo-b", source="vision:cam1", window_start=t,
                   window_end=t + timedelta(seconds=60),
                   occupants=[{"astronaut_id": "ast-01", "seconds_present": 60}],
                   received_at=t, simulated=False),
    ]
    rates = [hr(60 + i, t + timedelta(minutes=i)) for i in range(10)]
    rates.append(hr(30, t, "bad"))

    inputs = build_daily_inputs("ast-01", [], signals, vision, co, rates, SETTINGS)
    d = t.date()
    assert inputs.values["signal.hrv_sdnn"] == {d: 50}  # suspect and bad excluded
    assert inputs.excluded_suspect == 1
    assert inputs.origin(d) == "live"  # the bad simulated record is not used, so not counted
    assert inputs.values["vision.yawns_per_min"] == {d: 1.0}
    assert inputs.values["vision.perclos"] == {d: 0.1}
    # neutral_ok=False: metrics relative to the neutral are dropped.
    assert "vision.eye_openness_vs_neutral" not in inputs.values
    assert "vision.brow_lower_delta" not in inputs.values
    # Max own pair (45 s with an unknown) + a window alone (0 s).
    assert inputs.values["social.accompanied_minutes"] == {d: 0.75}
    # 10th percentile (nearest rank) of 60..69.
    assert inputs.values["onboard.heart_rate_low"] == {d: 60}


def test_heart_rate_low_needs_enough_readings() -> None:
    t = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    rates = [hr(70, t) for _ in range(9)]
    inputs = build_daily_inputs("ast-01", [], [], [], [], rates, SETTINGS)
    assert "onboard.heart_rate_low" not in inputs.values


def bitacora(i: int, brow: float, lip: float, brow_peak, lip_peak, neutral_ok=True):
    start = datetime.combine(day(i), datetime.min.time(), tzinfo=UTC).replace(hour=8)
    return VisionSession(
        id=i, astronaut_id="ast-01", session_type="bitacora", module_id="modulo-a",
        source="vision:cam0", started_at=start, ended_at=start + timedelta(seconds=90),
        quality="good", valid_frame_ratio=0.95, identity={"method": "face"},
        neutral_ok=neutral_ok,
        tension={"brow_lower_delta": brow, "lip_press_delta": lip,
                 "brow_lower_peak_1s": brow_peak, "lip_press_peak_1s": lip_peak},
        received_at=start, simulated=False,
    )


def test_tension_peaks_catch_brief_grimaces_the_mean_dilutes() -> None:
    def sessions(with_peaks: bool):
        out = []
        for i in range(DAYS):
            tense = i >= DERAIL
            # A few 1-2 s grimaces in a 90 s log barely move the session mean.
            brow, lip = (0.035, 0.03) if tense else (0.03 + 0.005 * (i % 2), 0.025)
            peaks = (0.45, 0.40) if tense else (0.10 + 0.02 * (i % 3), 0.08)
            out.append(bitacora(i, brow, lip, *(peaks if with_peaks else (None, None))))
        return out

    def stress(with_peaks: bool):
        inputs = build_daily_inputs("ast-01", [], [], sessions(with_peaks), [], [], SETTINGS)
        ev = evaluate(inputs, TODAY, SETTINGS)
        return ev, next(i for i in ev.indicators if i.kind == "stress")

    ev, ind = stress(with_peaks=True)
    assert ind.status == "attention" and ind.run and ind.run.start == day(DERAIL)
    assert ev.sustained_sources == ["vision"]

    ev, ind = stress(with_peaks=False)
    assert ind.status == "ok" and ev.level == "ok"


def test_tension_peaks_are_dropped_without_a_neutral() -> None:
    inputs = build_daily_inputs(
        "ast-01", [], [], [bitacora(0, 0.03, 0.02, 0.5, 0.5, neutral_ok=False)], [], [], SETTINGS
    )
    assert not any(k.startswith("vision.") for k in inputs.values)
