"""Self-check for the device simulator: python3 firmware/test_simulator.py"""

import random
import re
from datetime import UTC, datetime, timedelta

from simulator import CREW, Astronaut, Uplink, flash_log, urine_color

rng = random.Random(1)
now = datetime.now(UTC)
crew = [Astronaut(i, p, rng) for i, p in CREW.items()]
history = flash_log(crew, now, now - timedelta(days=30))

for r in history:
    assert (r["value"] is None) != (r["value_text"] is None), r
    assert r["quality"] in ("good", "suspect", "bad"), r
    assert r["recorded_at"] < now.isoformat(), r
hr = [r["value"] for r in history if r["kind"] == "heart_rate" and r["astronaut_id"] == "ast-01" and r["quality"] == "good"]
assert 50 < sum(hr) / len(hr) < 100, sum(hr) / len(hr)
rad = [r["value"] for r in history if r["kind"] == "urine_radiation_marker"]
assert len(rad) == 14 * len(CREW) and all(r > 0 for r in rad), rad
assert all(r["unit"] == "ng/mg creatinine" for r in history if r["kind"] == "urine_radiation_marker")
assert all(re.fullmatch(r"#[0-9A-F]{6}", urine_color(d)) for d in (0, 0.5, 1))
assert urine_color(0) == "#F5EC9A" and urine_color(1) == "#B8860B"

# API unreachable: readings stay buffered, nothing lost.
uplink = Uplink("http://127.0.0.1:9")
assert uplink.flush(history[:3]) == 0 and len(uplink.buffer) == 3 and not uplink.online
uplink.configure_radiation()  # API down: logs and returns, never raises
print("ok")
