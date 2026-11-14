"""Load a SIMULATED wellbeing history (source="simulated") for the demo.

Creates ast-01..ast-04 through the running onboard API if they are missing,
then writes check-ins, Watch-like signals and co-presence into wellbeing.db.
Rerunning replaces the previous simulated rows; live data is kept.

    uv run python scripts/simulate_wellbeing.py [--base http://127.0.0.1:8000] [--days 21]
"""

import argparse
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

from onboard_api.wellbeing.database import connect_wellbeing
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.settings import WellbeingSettings
from onboard_api.wellbeing.simulator import CREW, simulate


def ensure_astronaut(base: str, astronaut_id: str, name: str) -> None:
    request = urllib.request.Request(
        base + "/astronauts",
        data=json.dumps({"id": astronaut_id, "display_name": name}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=10).close()
    except urllib.error.HTTPError as error:
        if error.code != 409:  # 409: already registered, keep its name
            raise SystemExit(f"/astronauts -> HTTP {error.code}: {error.read().decode()}")
    except urllib.error.URLError as error:
        raise SystemExit(
            f"No se pudo conectar con {base} ({error.reason}). "
            "Arranca el servicio con: uv run fastapi dev"
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--perclos", type=float, nargs=2, metavar=("LOW", "HIGH"),
        help="resting PERCLOS range for simulated logs (pending recalibration)",
    )
    args = parser.parse_args()

    for astronaut_id, name in CREW.items():
        ensure_astronaut(args.base.rstrip("/"), astronaut_id, name)
    settings = WellbeingSettings()
    conn = connect_wellbeing(settings.db_path)
    try:
        simulate(
            WellbeingRepository(conn),
            datetime.now(UTC).date(),
            days=args.days,
            seed=args.seed,
            perclos=tuple(args.perclos) if args.perclos else None,
        )
    finally:
        conn.close()
    print(f"Historial SIMULADO de {args.days} días cargado en {settings.db_path}")


if __name__ == "__main__":
    main()
