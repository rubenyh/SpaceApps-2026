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
assert list(CREW) == ["ast-01"]
# Mock values stay inside the normal ranges.
for kind, low, high in (("heart_rate", 60, 100), ("spo2", 95, 100), ("urine_temperature", 32, 38),
                        ("urine_ph", 4.6, 8.0), ("urine_radiation_marker", 3.0, 5.5)):
    values = [r["value"] for r in history if r["kind"] == kind]
    assert values and all(low <= v <= high for v in values) and all(r["quality"] == "good" for r in history), kind
rad = [r["value"] for r in history if r["kind"] == "urine_radiation_marker"]
assert len(rad) == 14 * len(CREW) and all(r > 0 for r in rad), rad
assert all(r["unit"] == "ng/mg creatinine" for r in history if r["kind"] == "urine_radiation_marker")
assert all(re.fullmatch(r"#[0-9A-F]{6}", urine_color(d)) for d in (0, 0.5, 1))
assert urine_color(0) == "#F5EC9A" and urine_color(1) == "#B8860B"

# API unreachable: readings stay buffered, nothing lost.
uplink = Uplink("http://127.0.0.1:9")
assert uplink.flush(history[:3]) == 0 and len(uplink.buffer) == 3 and not uplink.online
uplink.configure_radiation()  # API down: logs and returns, never raises
# The ESP32 owns this astronaut's pH, salinity and temperature: only colour and 8-OHdG stay simulated.
assert len(crew[0].urine(now)) == 5
crew[0].real_urine = True
assert {r["kind"] for r in crew[0].urine(now)} == {"urine_color", "urine_radiation_marker"}

# Serial bridge parser, with lines as the board prints them.
from serial_bridge import parse_line

rows = parse_line("26.1;6.94;0;\r\n", "ast-01", now)
assert [(r["kind"], r["value"], r["unit"]) for r in rows] == [
    ("urine_temperature", 26.1, "°C"), ("urine_ph", 6.94, "pH"), ("urine_salinity", 0.0, "mg/L")], rows
assert rows[0]["quality"] == "suspect" and rows[1]["quality"] == "good"
assert all(r["source"] == "serial:urine-analyser" and r["astronaut_id"] == "ast-01" for r in rows)
assert parse_line("36.5;6.2;120", "ast-01", now)[0]["quality"] == "good"
for bad in ("", "26.1;6.9", "26.1;abc;0;", "\x00\xff;;;", "boot ok", "1;2;3;4;"):
    assert parse_line(bad, "ast-01", now) == [], bad
print("ok")
