"""SIMULATED wellbeing history for the demo. Every record has source="simulated".

Crew story (deterministic for a given seed):
  ast-01  stable.
  ast-02  derails from day DERAIL_DAY: check-in, physiology and social all drop
          -> "needs_support", onset on that day.
  ast-03  says "I'm fine" in the check-in, but physiology and social drop from
          day DISCREPANCY_DAY -> discrepancy.
  ast-04  stable, with a single bad day: an isolated reading never alerts.
No vision history is simulated: camera metrics in the demo are live.
"""

import random
from datetime import UTC, date, datetime, time, timedelta
from itertools import combinations

from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.schemas import CheckinUpsert, CoPresenceCreate, SignalCreate

CREW = {"ast-01": "X", "ast-02": "Y", "ast-03": "Z", "ast-04": "W"}
SOURCE = "simulated"
DERAIL_DAY = 14
DISCREPANCY_DAY = 15
BAD_DAY = 17


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


def clear_simulated(repo: WellbeingRepository) -> None:
    conn = repo._conn  # noqa: SLF001 - same module family, simulated rows only
    conn.execute("DELETE FROM checkins WHERE source = ?", (SOURCE,))
    conn.execute("DELETE FROM signals WHERE source = ?", (SOURCE,))
    conn.execute(
        "DELETE FROM co_presence WHERE json_extract(body, '$.source') = ?", (SOURCE,)
    )


def simulate(repo: WellbeingRepository, today: date, days: int = 21, seed: int = 7) -> None:
    """Replace previous simulated rows with `days` days of history ending today."""
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
                submitted_at=_at(day, 21),
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
                        recorded_at=_at(day, hour),
                        quality="good",
                        source=SOURCE,
                    ),
                    received_at=_at(day, hour, 5),
                )

        # Six 30-minute shared slots per day (meals, briefings, leisure).
        withdrawn = {aid for aid, flag in derailed.items() if flag}
        # Withdrawn crew join one random slot a day; the rest join all.
        joined = {aid: rng.randrange(6) for aid in withdrawn}
        for slot in range(6):
            present = [aid for aid in CREW if aid not in withdrawn or joined[aid] == slot]
            if not present:
                continue
            begin = _at(day, 8 + 2 * slot)
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
