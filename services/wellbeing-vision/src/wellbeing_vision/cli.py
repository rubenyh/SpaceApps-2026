import argparse
import re
from pathlib import Path

from wellbeing_vision.config import ASTRONAUT_ID_PATTERN, Settings
from wellbeing_vision.download import download_models
from wellbeing_vision.sink import Sink


def _astronaut(value: str) -> str:
    if not re.fullmatch(ASTRONAUT_ID_PATTERN, value):
        raise argparse.ArgumentTypeError(f"invalid astronaut id: {value}")
    return value


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(prog="wellbeing-vision")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models", help="download model files into models_dir")

    bit = sub.add_parser("bitacora", help="daily video log with live preview")
    bit.add_argument("--astronaut", type=_astronaut, required=True)
    bit.add_argument("--camera", type=int, default=0)
    bit.add_argument("--seconds", type=float, default=60.0)
    bit.add_argument("--dry-run", action="store_true", help="print JSON instead of POSTing")
    bit.add_argument("--out", type=Path, help="with --dry-run, also append JSON lines here")

    args = parser.parse_args()
    if args.cmd == "models":
        download_models(settings.models_dir)
        return

    if args.astronaut not in settings.astronauts:
        parser.error(f"{args.astronaut} is not in the configured crew: {', '.join(settings.astronauts)}")
    sink = Sink(settings.api_url, settings.outbox_path, dry_run=args.dry_run, dry_run_file=args.out)
    if args.cmd == "bitacora":
        from wellbeing_vision.bitacora import run_bitacora  # imports MediaPipe only when needed

        if run_bitacora(settings, sink, args.astronaut, args.camera, args.seconds) is None:
            raise SystemExit(1)
