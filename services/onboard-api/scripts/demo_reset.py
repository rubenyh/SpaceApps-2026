"""Reset the wellbeing demo in one step (idempotent). Run from services/onboard-api
with the API already running from the same folder (`uv run fastapi dev`):

    uv run python scripts/demo_reset.py [--base http://127.0.0.1:8000] [--perclos LOW HIGH]

1. Checks the API is up and serves the wellbeing routes.
2. Backs up data/wellbeing.db to data/backups/ and empties its tables (schema kept,
   onboard.db untouched).
3. Loads the SIMULATED history (seed 7) and the synthetic Watch export for ast-01,
   shifted so it ends yesterday.
4. Checks ast-01 is ready for today's live log and prints the crew status.
"""

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from import_apple_health import post as post_signal
from simulate_wellbeing import ensure_astronaut

from onboard_api.wellbeing.database import connect_wellbeing
from onboard_api.wellbeing.health_import import iter_signals, open_export
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.settings import WellbeingSettings
from onboard_api.wellbeing.simulator import CREW, simulate

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "apple_health" / "export.xml"
SAMPLE_SOURCE = "simulated:apple_health_sample"
# Children first, so foreign keys never block the wipe.
TABLES = ("co_presence_members", "co_presence", "vision_sessions", "signals", "checkins",
          "ground_packages")


def get(base: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{path} -> HTTP {error.code}: {error.read().decode()}") from error
    except urllib.error.URLError as error:
        raise SystemExit(
            f"La API no responde en {base} ({error.reason}). "
            "Arranca primero: uv run fastapi dev (desde services/onboard-api)"
        ) from error


def backup_and_wipe(db_path: Path) -> Path | None:
    backup = None
    if db_path.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%SZ")
        backup = db_path.parent / "backups" / f"wellbeing-{stamp}.db"
        backup.parent.mkdir(parents=True, exist_ok=True)
        source, target = sqlite3.connect(db_path), sqlite3.connect(backup)
        try:
            source.backup(target)  # consistent copy, WAL included
        finally:
            target.close()
            source.close()
    conn = connect_wellbeing(db_path)  # creates and migrates if missing
    try:
        conn.execute("BEGIN")
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("COMMIT")
    finally:
        conn.close()
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--perclos", type=float, nargs=2, metavar=("LOW", "HIGH"))
    args = parser.parse_args()
    base = args.base.rstrip("/")

    get(base, "/wellbeing/parameters")
    settings = WellbeingSettings()
    backup = backup_and_wipe(settings.db_path)
    print(f"Respaldo: {backup or '(no había wellbeing.db)'}")

    for astronaut_id, name in CREW.items():
        ensure_astronaut(base, astronaut_id, name)
    today = datetime.now(UTC).date()
    conn = connect_wellbeing(settings.db_path)
    try:
        simulate(WellbeingRepository(conn), today, seed=7,
                 perclos=tuple(args.perclos) if args.perclos else None)
    finally:
        conn.close()
    print(f"Historial SIMULADO cargado (21 días, semilla 7) en {settings.db_path}")

    with open_export(SAMPLE) as stream:
        signals = list(iter_signals(stream, "ast-01", source=SAMPLE_SOURCE))
    shift = (today - timedelta(days=1)) - max(s.recorded_at.date() for s in signals)
    for signal in signals:
        moved = signal.model_copy(update={"recorded_at": signal.recorded_at + shift})
        post_signal(base, moved.model_dump_json().encode())
    print(f"Export de ejemplo del Watch importado para ast-01: {len(signals)} señales (SIMULADO)")

    ast01 = get(base, "/astronauts/ast-01/wellbeing")
    # Only what a daily log measures (motion comes from ambient cameras).
    log = [c for i in ast01["indicators"] if i["kind"] in ("fatigue", "stress")
           for c in i["components"] if c["source"] == "vision"]
    ready = [c for c in log if c["baseline_ready"]]
    live_today = [c for c in log if c["latest_day"] == today.isoformat()]
    print(
        f"ast-01 listo para la bitácora en vivo: {len(ready)}/{len(log)} métricas de la "
        f"bitácora con línea base formada, {len(live_today)} con datos de hoy."
    )

    crew = get(base, "/wellbeing/crew")["members"]
    print(f"\n{'astronauta':<11}{'nivel':<17}{'inicio':<12}{'discrepancia':<14}fuentes sostenidas")
    for member in crew:
        detail = get(base, f"/astronauts/{member['astronaut_id']}/wellbeing")
        print(
            f"{member['astronaut_id']:<11}{detail['level']:<17}{detail['onset_date'] or '-':<12}"
            f"{'sí' if detail['discrepancy'] else 'no':<14}"
            f"{', '.join(detail['sustained_sources']) or '-'}"
        )
    if all(m["level"] == "no_data" for m in crew if m["astronaut_id"] in CREW):
        sys.exit(
            "\nAVISO: la API no ve los datos. Arráncala desde services/onboard-api "
            "(la misma carpeta que este script) para que use el mismo wellbeing.db."
        )


if __name__ == "__main__":
    main()
