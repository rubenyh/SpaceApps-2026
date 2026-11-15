"""Import HRV (SDNN), resting heart rate and sleep from an Apple Health export.

Streams export.zip (or export.xml) and sends each signal to
POST /wellbeing/signals of a running onboard API, for one astronaut.

    uv run python scripts/import_apple_health.py export.zip --astronaut ast-01
    uv run python scripts/import_apple_health.py samples/apple_health/export.xml \
        --astronaut ast-01 --source simulated:apple_health_sample   # synthetic sample
    ... --since 2026-10-01 --dry-run --base http://127.0.0.1:8000
"""

import argparse
import urllib.error
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

from onboard_api.wellbeing.health_import import DEFAULT_SOURCE, iter_signals, open_export


def post(base: str, body: bytes) -> None:
    request = urllib.request.Request(
        base + "/wellbeing/signals", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=10).close()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"/wellbeing/signals -> HTTP {error.code}: {error.read().decode()}")
    except urllib.error.URLError as error:
        raise SystemExit(
            f"No se pudo conectar con {base} ({error.reason}). "
            "Arranca el servicio con: uv run fastapi dev"
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="export.zip or export.xml")
    parser.add_argument("--astronaut", required=True, help="astronaut_id, e.g. ast-01")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--since", type=date.fromisoformat, help="YYYY-MM-DD (UTC day)")
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="use simulated:<name> for synthetic exports so they show as SIMULADO",
    )
    parser.add_argument("--dry-run", action="store_true", help="count only, send nothing")
    args = parser.parse_args()

    counts: Counter[str] = Counter()
    with open_export(args.export) as stream:
        for signal in iter_signals(stream, args.astronaut, args.since, args.source):
            if not args.dry_run:
                post(args.base.rstrip("/"), signal.model_dump_json().encode())
            counts[signal.kind] += 1
    action = "Contadas (sin enviar)" if args.dry_run else "Enviadas"
    print(f"{action} para {args.astronaut}: {dict(counts) or 'ninguna señal'}")


if __name__ == "__main__":
    main()
