"""SIMULATED wellbeing history for the demo. Every record has source="simulated".

Crew story (deterministic for a given seed):
  ast-01  stable.
  ast-02  derails from day DERAIL_DAY: check-in, physiology and social all drop
          -> "needs_support", onset on that day.
  ast-03  says "I'm fine" in the check-in, but physiology and social drop from
          day DISCREPANCY_DAY -> discrepancy.
  ast-04  stable, with a single bad day: an isolated reading never alerts.
Vision (daily logs) follows the same story and stops at yesterday, so a live
log recorded today is judged alone against an already formed baseline.
"""

import random
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from itertools import combinations

from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.schemas import (
    CheckinUpsert,
    CoPresenceCreate,
    SignalCreate,
    VisionSessionCreate,
)

CREW = {"ast-01": "X", "ast-02": "Y", "ast-03": "Z", "ast-04": "W"}
SOURCE = "simulated"
DERAIL_DAY = 14
DISCREPANCY_DAY = 15
BAD_DAY = 17

# Daily-log (bitacora) ranges, uniform (low, high). Simulation parameters, not
# clinical ranges. ALL PROVISIONAL until logs from the corrected vision build
# (more robust neutral calibration, speech-filtered lips) are measured.
# Source: 3 rest logs, new build, 60 s at ~50 cm, reading/talking naturally,
# no grimaces (data/rest.jsonl of wellbeing-vision, 2026-11-15): S1, S2, S3.
VISION_REST = {
    "blink_rate_per_min": (19.0, 26.0),  # S1-S3: 26.0, 23.2, 19.5 (talking/reading)
    # S1 0.949, S2 0.925. S3 (1.24) left out: its neutral calibration was biased.
    "eye_openness_vs_neutral": (0.90, 1.05),
    "yawn_count": (0, 2),  # 0 in S1-S3; up to 2 in the first session
    "nod_count": (0, 2),  # 0 in S1-S3; up to 2 in the first session
    # S1-S3: 0.183, 0.122, 0.065. Kept wide on purpose: it swings with each
    # session's neutral calibration. Override with simulate(perclos=...) / --perclos.
    "perclos": (0.06, 0.19),
    "brow_lower_delta": (0.015, 0.03),  # S1-S3: 0.015, 0.029, 0.020
    "brow_lower_peak_1s": (0.045, 0.13),  # S1-S3: 0.046, 0.129, 0.094 (acted: 0.663)
    # Stored but not scored: talking alone peaks at 0.41-0.49.
    "lip_press_delta": (0.035, 0.09),  # S1-S3: 0.047, 0.090, 0.039
    "lip_press_peak_1s": (0.41, 0.49),  # S1-S3: 0.459, 0.492, 0.414
}
# Altered days (more fatigue and tension). Assumed, for the demo story only.
# PERCLOS on altered days is derived from the rest range (see _vision_ranges).
VISION_ALTERED = {
    "blink_rate_per_min": (19.0, 26.0),
    "eye_openness_vs_neutral": (0.70, 0.80),
    "yawn_count": (2, 4),
    "nod_count": (2, 4),
    "brow_lower_delta": (0.06, 0.10),
    "brow_lower_peak_1s": (0.35, 0.65),  # acted reference peak: 0.663
    "lip_press_delta": (0.035, 0.09),  # not scored
    "lip_press_peak_1s": (0.41, 0.49),  # not scored
}


def _at(day: date, hour: int, minute: int = 0, tz: tzinfo = UTC) -> datetime:
    """Local clock time on a mission day (stored later in UTC)."""
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


def clear_simulated(repo: WellbeingRepository) -> None:
    conn = repo._conn  # noqa: SLF001 - same module family, simulated rows only
    conn.execute("DELETE FROM checkins WHERE source = ?", (SOURCE,))
    conn.execute("DELETE FROM signals WHERE source = ?", (SOURCE,))
    conn.execute(
        "DELETE FROM co_presence WHERE json_extract(body, '$.source') = ?", (SOURCE,)
    )
    conn.execute(
        "DELETE FROM vision_sessions WHERE json_extract(body, '$.source') = ?", (SOURCE,)
    )


def _vision_ranges(
    perclos: tuple[float, float] | None,
) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    low, high = perclos or VISION_REST["perclos"]
    if not 0 <= low < high <= 1:
        raise ValueError(f"perclos range must satisfy 0 <= low < high <= 1, got {perclos}")
    rest = {**VISION_REST, "perclos": (low, high)}
    altered = {**VISION_ALTERED, "perclos": (min(1.0, high + 0.10), min(1.0, high + 0.20))}
    return rest, altered


def simulate(
    repo: WellbeingRepository,
    today: date,
    days: int = 21,
    seed: int = 7,
    perclos: tuple[float, float] | None = None,
    tz: tzinfo = UTC,
) -> None:
    """Replace previous simulated rows with `days` days of history ending today.

    today: mission day in `tz` (the API's WELLBEING_MISSION_TZ). Every record
    gets a local clock time on its day, so it never slips into the next day.
    perclos: resting PERCLOS range for the daily logs (default VISION_REST).
    """
    vision_rest, vision_altered = _vision_ranges(perclos)
    rng = random.Random(seed)
    clear_simulated(repo)
    start = today - timedelta(days=days - 1)

    def jitter(base: int) -> int:
        return max(0, min(4, base + rng.choice((0, 0, 0, 1, -1))))

    for i in range(days):
        day = start + timedelta(days=i)
        derailed = {
            "ast-02": i >= DERAIL_DAY,
            "ast-03": i >= DISCREPANCY_DAY,  # passive signals only
        }
        for aid in CREW:
            low = aid == "ast-02" and derailed["ast-02"]
            bad_day = aid == "ast-04" and i == BAD_DAY
            down = low or bad_day
            repo.upsert_checkin(
                aid,
                day,
                CheckinUpsert(
                    sleep_hours=rng.choice((4.5, 5.0)) if down else rng.choice((7.0, 7.5, 8.0)),
                    sleep_quality=1 if down else jitter(3),
                    energy=1 if down else jitter(3),
                    mood=1 if down else jitter(3),
                    interest=1 if down else jitter(3),
                    stress=4 if down else jitter(1),
                    crew_connection=1 if down else jitter(3),
                    source=SOURCE,
                ),
                submitted_at=_at(day, 21, tz=tz),
            )
            passive_low = low or derailed.get(aid, False) and aid == "ast-03"
            for kind, value, unit, hour in (
                ("hrv_sdnn", (36 if passive_low else 55) + rng.gauss(0, 2), "ms", 7),
                ("resting_heart_rate", (66 if passive_low else 58) + rng.gauss(0, 1), "bpm", 7),
                ("sleep_hours", (5.0 if passive_low else 7.3) + rng.gauss(0, 0.2), "h", 6),
            ):
                repo.create_signal(
                    SignalCreate(
                        astronaut_id=aid,
                        kind=kind,
                        value=round(max(0.0, value), 1),
                        unit=unit,
                        recorded_at=_at(day, hour, tz=tz),
                        quality="good",
                        source=SOURCE,
                    ),
                    received_at=_at(day, hour, 5, tz=tz),
                )
            if i < days - 1:  # leave today free for a live log
                altered = passive_low or bad_day
                repo.create_vision_session(
                    _bitacora(aid, _at(day, 8, tz=tz), vision_altered if altered else vision_rest, rng),
                    received_at=_at(day, 8, 2, tz=tz),
                )

        # Six 30-minute shared slots per day (meals, briefings, leisure).
        withdrawn = {aid for aid, flag in derailed.items() if flag}
        # Withdrawn crew join one random slot a day; the rest join all.
        joined = {aid: rng.randrange(6) for aid in withdrawn}
        for slot in range(6):
            present = [aid for aid in CREW if aid not in withdrawn or joined[aid] == slot]
            if not present:
                continue
            begin = _at(day, 8 + 2 * slot, tz=tz)
            repo.create_co_presence(
                CoPresenceCreate(
                    module_id="modulo-a" if slot % 2 == 0 else "modulo-b",
                    source=SOURCE,
                    window_start=begin,
                    window_end=begin + timedelta(minutes=30),
                    occupants=[{"astronaut_id": a, "seconds_present": 1800} for a in present],
                    pairs=[
                        {"a": a, "b": b, "seconds_together": 1800}
                        for a, b in combinations(present, 2)
                    ],
                ),
                received_at=begin + timedelta(minutes=31),
            )


def _bitacora(
    aid: str, begin: datetime, ranges: dict[str, tuple[float, float]], rng: random.Random
) -> VisionSessionCreate:
    def u(key: str) -> float:
        return round(rng.uniform(*ranges[key]), 3)

    def n(key: str) -> int:
        return rng.randint(*map(int, ranges[key]))

    return VisionSessionCreate(
        astronaut_id=aid,
        session_type="bitacora",
        module_id="modulo-a",
        source=SOURCE,
        started_at=begin,
        ended_at=begin + timedelta(seconds=90),
        quality="good",
        valid_frame_ratio=0.95,
        identity={"method": "face", "match_score": 0.8},
        neutral_ok=True,
        fatigue={
            "blink_rate_per_min": u("blink_rate_per_min"),
            "perclos": u("perclos"),
            "eye_openness_vs_neutral": u("eye_openness_vs_neutral"),
            "yawn_count": n("yawn_count"),
            "nod_count": n("nod_count"),
        },
        tension={
            "brow_lower_delta": u("brow_lower_delta"),
            "lip_press_delta": u("lip_press_delta"),
            "brow_lower_peak_1s": u("brow_lower_peak_1s"),
            "lip_press_peak_1s": u("lip_press_peak_1s"),
        },
    )
