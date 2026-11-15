"""Software stand-in for the crew biomonitor hardware.

Behaves like the device firmware would once it exists: one wearable per
astronaut (pulse oximeter: heart rate + SpO2), a shared urine analyser and a
muscle scanner. Each sensor follows a simple physiological model, measurements
go to onboard-api `POST /readings` with source "simulated:<sensor>" (marked simulated, see db/data-dictionary.md), and the
console reads them from the API as it would with the real device.

On boot the device uploads its flash log (recent history), then measures live.
If the API is down, readings stay in the device buffer and are retried.

Simulated data, not clinically validated. Stdlib only:

    python3 firmware/simulator.py                    # API on 127.0.0.1:8000
    python3 firmware/simulator.py --urine-every 120  # faster urine samples
    python3 firmware/simulator.py --real-vitals ast-01  # ast-01 wears a real Apple Watch
    python3 firmware/simulator.py --real-urine ast-01   # ast-01's urine pH/salinity/temp from the ESP32
"""

import argparse
import json
import math
import random
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import UTC, datetime, timedelta

DEVICE_ID = "biomon-sim-01"
# Per astronaut: display name, resting HR, SpO2, starting muscle density and urinary 8-OHdG.
# ast-02 rests above the 60-100 bpm range so the console shows an alert, and its 8-OHdG
# sits at the top of the range so some samples come out high.
CREW = {
    "ast-01": {"name": "Demo Uno", "hr": 72, "spo2": 98.0, "muscle": 42.0, "ohdg": 4.0},
    "ast-02": {"name": "Demo Dos", "hr": 108, "spo2": 96.0, "muscle": 40.5, "ohdg": 5.4},
}
# Urine radiation marker: 8-OHdG (oxidative DNA damage, raised by ionizing radiation).
# Indirect marker, not a dose. Range: healthy-adult IQR, chemical methods (Graille et al. 2020).
RADIATION_CONFIG = {
    "unit": "ng/mg creatinine",
    "stale_after_seconds": 86400,
    "normal_min": 3.0,
    "normal_max": 5.5,
    "range_role": "health",
    "provisional": True,
    "range_source": "Graille et al. 2020 (8-OHdG meta-analysis)",
}
MUSCLE_LOSS_PER_DAY = 0.09  # u.a./day, microgravity atrophy trend


class Astronaut:
    real_vitals = False  # True: a real wearable (apps/watch-app) sends this astronaut's pulse-ox
    real_urine = False  # True: the ESP32 analyser (serial_bridge.py) sends this astronaut's pH, salinity, temperature

    def __init__(self, astronaut_id: str, profile: dict, rng: random.Random):
        self.id = astronaut_id
        self.profile = profile
        self.rng = rng
        self.hr = float(profile["hr"])
        self.spo2 = profile["spo2"]
        self.exercise_until: datetime | None = None
        self.hydration = rng.uniform(0.4, 0.8)  # 0 dry .. 1 well hydrated

    def vitals(self, when: datetime) -> list[dict]:
        if self.real_vitals:
            return []
        rng = self.rng
        if self.exercise_until is None and rng.random() < 0.004:
            self.exercise_until = when + timedelta(minutes=rng.randint(3, 8))
        exercising = self.exercise_until is not None and when < self.exercise_until
        if not exercising:
            self.exercise_until = None
        # Mean-reverting walk around the resting value (or a workout target).
        target = self.profile["hr"] + (45 if exercising else 0)
        self.hr += 0.15 * (target - self.hr) + rng.gauss(0, 1.5)
        self.spo2 += 0.2 * (self.profile["spo2"] - (1.5 if exercising else 0) - self.spo2) + rng.gauss(0, 0.3)

        if rng.random() < 0.01:  # probe off the finger: firmware sends nothing
            return []
        quality = "good"
        hr, spo2 = self.hr, self.spo2
        if rng.random() < 0.03:  # motion artifact
            quality = "suspect"
            hr += rng.gauss(0, 15)
            spo2 -= abs(rng.gauss(0, 3))
        return [
            reading(self.id, "heart_rate", "bpm", when, value=max(30, round(hr)), quality=quality, source="simulated:pulse-ox"),
            reading(self.id, "spo2", "%", when, value=min(100, max(70, round(spo2))), quality=quality, source="simulated:pulse-ox"),
        ]

    def urine(self, when: datetime) -> list[dict]:
        rng = self.rng
        self.hydration = min(1.0, max(0.0, self.hydration + rng.gauss(0, 0.1)))
        dry = 1 - self.hydration
        salinity = round(10 + 18 * dry + rng.gauss(0, 1.5), 1)
        ph = round(6.2 + rng.gauss(0, 0.4), 1)
        temperature = round(36.0 - rng.uniform(0, 2.5) - (6 if rng.random() < 0.05 else 0), 1)
        temp_quality = "good" if 32 <= temperature <= 38 else "suspect"  # sample_validity range
        source = "simulated:urine-analyser"
        out = [
            reading(self.id, "urine_color", "rgb_hex", when, value_text=urine_color(dry), source=source),
            reading(self.id, "urine_radiation_marker", RADIATION_CONFIG["unit"], when,
                    value=max(0.5, round(self.profile["ohdg"] + rng.gauss(0, 0.5), 2)), source=source),
        ]
        if not self.real_urine:
            out += [
                reading(self.id, "urine_ph", "pH", when, value=ph, source=source),
                reading(self.id, "urine_salinity", "mS/cm", when, value=salinity, source=source),
                reading(self.id, "urine_temperature", "°C", when, value=temperature, quality=temp_quality, source=source),
            ]
        return out

    def muscle(self, when: datetime, boot: datetime) -> list[dict]:
        days = (when - boot).total_seconds() / 86400
        value = round(self.profile["muscle"] - MUSCLE_LOSS_PER_DAY * days + self.rng.gauss(0, 0.15), 2)
        # Unit is a placeholder until the scanner's real unit is defined.
        return [reading(self.id, "muscle_density", "u.a.", when, value=value, source="simulated:muscle-scanner")]


def urine_color(dry: float) -> str:
    """Pale straw when hydrated, dark amber when dehydrated."""
    pale, amber = (0xF5, 0xEC, 0x9A), (0xB8, 0x86, 0x0B)
    return "#" + "".join(f"{round(p + (a - p) * dry):02X}" for p, a in zip(pale, amber))


def reading(astronaut, kind, unit, when, value=None, value_text=None, quality="good", source="device"):
    return {
        "astronaut_id": astronaut,
        "kind": kind,
        "value": value,
        "value_text": value_text,
        "unit": unit,
        "recorded_at": when.isoformat(),
        "quality": quality,
        "source": source,
    }


class Uplink:
    """Sends readings to onboard-api. Keeps unsent ones buffered, like device flash."""

    def __init__(self, base_url: str, capacity: int = 10_000):
        self.base_url = base_url.rstrip("/")
        self.buffer: deque[dict] = deque(maxlen=capacity)  # oldest dropped when full
        self.online = True

    def post(self, path: str, body: dict) -> None:
        request = urllib.request.Request(
            self.base_url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=5):
            pass

    def register_crew(self) -> bool:
        try:
            for astronaut_id, profile in CREW.items():
                try:
                    self.post("/astronauts", {"id": astronaut_id, "display_name": profile["name"]})
                except urllib.error.HTTPError as error:
                    if error.code != 409:  # 409: already registered
                        raise
            return True
        except (urllib.error.URLError, OSError) as error:
            log(f"crew registration failed ({error}), retrying")
            return False

    def configure_radiation(self) -> None:
        """Set unit and range of the 8-OHdG marker, unless an operator already set a unit."""
        try:
            with urllib.request.urlopen(self.base_url + "/sensors", timeout=5) as response:
                configs = {c["kind"]: c for c in json.load(response)}
            if configs.get("urine_radiation_marker", {}).get("unit") is None:
                request = urllib.request.Request(
                    self.base_url + "/sensors/urine_radiation_marker",
                    data=json.dumps(RADIATION_CONFIG).encode(),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                urllib.request.urlopen(request, timeout=5).close()
                log("radiation marker configured (8-OHdG, ng/mg creatinine)")
        except (urllib.error.URLError, OSError, ValueError) as error:
            # Unit NULL accepts any unit, so readings still go through without a range.
            log(f"radiation marker config failed ({error}), sending without a range")

    def flush(self, readings: list[dict]) -> int:
        self.buffer.extend(readings)
        sent = 0
        while self.buffer:
            try:
                self.post("/readings", self.buffer[0])
            except urllib.error.HTTPError as error:
                # Rejected by the API: retrying will not help, drop it.
                log(f"rejected {self.buffer[0]['kind']}: HTTP {error.code} {error.read().decode()[:200]}")
            except (urllib.error.URLError, OSError) as error:
                if self.online:
                    log(f"uplink down ({getattr(error, 'reason', error)}), buffering")
                self.online = False
                return sent
            else:
                sent += 1
            self.buffer.popleft()
        if not self.online:
            log("uplink restored, buffer flushed")
        self.online = True
        return sent


def log(message: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {DEVICE_ID}: {message}", flush=True)


def flash_log(crew: list[Astronaut], now: datetime, boot: datetime) -> list[dict]:
    """History the device recorded before the uplink came up, oldest first."""
    out = []
    for a in crew:
        for day in range(30, 0, -1):
            out += a.muscle(now - timedelta(days=day, hours=2), boot)
        for day in range(14, 0, -1):
            out += a.urine(now - timedelta(days=day, hours=3))
        for step in range(60, 0, -1):
            out += a.vitals(now - timedelta(seconds=15 * step))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="onboard-api base URL")
    parser.add_argument("--vitals-every", type=float, default=5, help="seconds between pulse-ox samples")
    parser.add_argument("--urine-every", type=float, default=600, help="seconds between urine samples")
    parser.add_argument("--muscle-every", type=float, default=3600, help="seconds between muscle scans")
    parser.add_argument("--no-history", action="store_true", help="skip the flash-log upload on boot")
    parser.add_argument("--real-vitals", action="append", default=[], choices=list(CREW), metavar="ID",
                        help="astronaut whose pulse-ox comes from a real watch: no simulated heart rate/SpO2 (repeatable)")
    parser.add_argument("--real-urine", action="append", default=[], choices=list(CREW), metavar="ID",
                        help="astronaut whose urine pH/salinity/temperature come from the ESP32 (serial_bridge.py); colour and 8-OHdG stay simulated (repeatable)")
    parser.add_argument("--seed", type=int, help="random seed for reproducible runs")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    uplink = Uplink(args.url)
    now = datetime.now(UTC)
    boot = now - timedelta(days=30)  # muscle trend starts 30 days ago
    crew = [Astronaut(i, p, rng) for i, p in CREW.items()]
    for a in crew:
        a.real_vitals = a.id in args.real_vitals
        a.real_urine = a.id in args.real_urine

    log(f"boot, crew {', '.join(CREW)}, uplink {args.url}")
    while not uplink.register_crew():
        time.sleep(5)
    uplink.configure_radiation()
    pending = [] if args.no_history else flash_log(crew, now, boot)
    log(f"uploading flash log ({len(pending)} readings)")
    log(f"sent {uplink.flush(pending)}")

    next_urine = next_muscle = 0.0  # take one of each right after boot
    try:
        while True:
            tick = time.monotonic()
            when = datetime.now(UTC)
            batch = [r for a in crew for r in a.vitals(when)]
            if tick >= next_urine:
                batch += [r for a in crew for r in a.urine(when)]
                next_urine = tick + args.urine_every
            if tick >= next_muscle:
                batch += [r for a in crew for r in a.muscle(when, boot)]
                next_muscle = tick + args.muscle_every
            hr = ", ".join(f"{a.id} real watch" if a.real_vitals else f"{a.id} {a.hr:.0f} bpm" for a in crew)
            log(f"{hr} | sent {uplink.flush(batch)}, buffered {len(uplink.buffer)}")
            time.sleep(max(0.0, args.vitals_every - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        log("shutdown")


if __name__ == "__main__":
    main()
