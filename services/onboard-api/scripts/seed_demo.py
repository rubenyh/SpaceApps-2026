"""Load DEMO data into a running onboard-api so the console has something to show.

Everything here is made up for UI testing: values, and the units of the sensors
whose real unit is still undefined (muscle density, salinity). Readings are
tagged source="demo". Do not use on a database that holds real readings.

    uv run python scripts/seed_demo.py           # history + current values
    uv run python scripts/seed_demo.py --live    # then keep sending vitals every 5 s

Vitals go stale after 5 minutes: rerun, or use --live, to keep them fresh.
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

ASTRONAUTS = {"ast-01": "Demo Uno", "ast-02": "Demo Dos"}
# Resting heart rate centre per astronaut: ast-02 sits above the 60-100 range.
HEART_RATE = {"ast-01": 72, "ast-02": 108}
SPO2 = {"ast-01": 98, "ast-02": 96}


def post(base: str, path: str, body: dict) -> int:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        if error.code == 409:  # astronaut already exists
            return 409
        raise SystemExit(f"{path} -> HTTP {error.code}: {error.read().decode()}") from error
    except urllib.error.URLError as error:
        raise SystemExit(
            f"No se pudo conectar con {base} ({error.reason}). "
            "Arranca el servicio con: uv run fastapi dev"
        ) from error


def reading(base, astronaut, kind, unit, when, value=None, value_text=None, quality="good"):
    post(
        base,
        "/readings",
        {
            "astronaut_id": astronaut,
            "kind": kind,
            "value": value,
            "value_text": value_text,
            "unit": unit,
            "recorded_at": when.isoformat(),
            "quality": quality,
            "source": "demo",
        },
    )


def vitals(base, astronaut, when):
    reading(base, astronaut, "heart_rate", "bpm", when, round(HEART_RATE[astronaut] + random.gauss(0, 3)))
    reading(base, astronaut, "spo2", "%", when, min(100, round(SPO2[astronaut] + random.gauss(0, 0.7))))


def seed(base: str) -> None:
    now = datetime.now(UTC)
    for astronaut, name in ASTRONAUTS.items():
        post(base, "/astronauts", {"id": astronaut, "display_name": name})

        # Last 15 minutes of vitals, one sample every 15 s.
        for step in range(60, -1, -1):
            vitals(base, astronaut, now - timedelta(seconds=15 * step))

        # 30 days of muscle density, slowly declining. Unit is a placeholder.
        for day in range(30, -1, -1):
            value = round(42.0 - 0.09 * (30 - day) + random.gauss(0, 0.15), 2)
            reading(base, astronaut, "muscle_density", "u.a.", now - timedelta(days=day, hours=2), value)

    # ast-01: 14 days of urine samples, the latest 3 hours old.
    for day in range(14, -1, -1):
        when = now - timedelta(days=day, hours=3)
        reading(base, "ast-01", "urine_ph", "pH", when, round(6.1 + random.gauss(0, 0.3), 1))
        reading(base, "ast-01", "urine_salinity", "mS/cm", when, round(18 + random.gauss(0, 2.5), 1))
    latest = now - timedelta(hours=3)
    reading(base, "ast-01", "urine_color", "rgb_hex", latest, value_text="#D9C24A")
    reading(base, "ast-01", "urine_temperature", "°C", latest, 35.8)

    # ast-02: one urine sample 26 hours old (stale), cold sample of suspect quality.
    old = now - timedelta(hours=26)
    reading(base, "ast-02", "urine_ph", "pH", old, 8.4)
    reading(base, "ast-02", "urine_salinity", "mS/cm", old, 24.3)
    reading(base, "ast-02", "urine_color", "rgb_hex", old, value_text="#B8860B")
    reading(base, "ast-02", "urine_temperature", "°C", old, 29.5, quality="suspect")
    # urine_radiation_marker is left without data on purpose: no marker is defined.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--live", action="store_true", help="keep sending vitals every 5 s")
    args = parser.parse_args()

    seed(args.url)
    print(f"Datos demo cargados en {args.url}: {', '.join(ASTRONAUTS)}")
    if args.live:
        print("Enviando signos vitales cada 5 s. Ctrl+C para parar.")
        try:
            while True:
                time.sleep(5)
                for astronaut in ASTRONAUTS:
                    vitals(args.url, astronaut, datetime.now(UTC))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
