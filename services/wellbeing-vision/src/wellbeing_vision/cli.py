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
    bit.add_argument("--mirror", action=argparse.BooleanOptionalAction, default=True,
                     help="mirror the preview (default on); text is never mirrored")
    bit.add_argument("--trace", type=Path, help="CSV of per-frame derived numbers (no images) for tuning")
    bit.add_argument("--dry-run", action="store_true", help="print JSON instead of POSTing")
    bit.add_argument("--out", type=Path, help="with --dry-run, also append JSON lines here")

    enr = sub.add_parser("enroll", help="enroll an astronaut's face (templates stay in data/faces/)")
    enr.add_argument("--astronaut", type=_astronaut, required=True)
    enr.add_argument("--camera", type=int, default=0)
    enr.add_argument("--samples", type=int, default=10)

    ide = sub.add_parser("identify", help="multi-person identity preview with poses (sends nothing)")
    ide.add_argument("--camera", type=int, default=0)
    ide.add_argument("--seconds", type=float, default=0.0, help="0 = until q/Esc")
    ide.add_argument("--rotate", type=int, choices=(0, 90, 180, 270),
                     help="fix the orientation (e.g. 180: camera or crew upside down); default: search all")

    amb = sub.add_parser("ambiente", help="ambient mode: co-presence and motion per module, with preview")
    amb.add_argument("--cameras", type=int, nargs="+", default=sorted(settings.cameras),
                     help="camera indexes; each is the module in WELLBEING_VISION_CAMERAS (default: all)")
    amb.add_argument("--window", type=float, default=60.0, help="seconds per co-presence window")
    amb.add_argument("--rotate", type=int, choices=(0, 90, 180, 270),
                     help="fix the orientation for every camera; default: search all")
    amb.add_argument("--seconds", type=float, default=0.0, help="0 = until q/Esc")
    amb.add_argument("--dry-run", action="store_true", help="print JSON instead of POSTing")
    amb.add_argument("--out", type=Path, help="with --dry-run, also append JSON lines here")

    args = parser.parse_args()
    if args.cmd == "models":
        download_models(settings.models_dir)
        return
    if args.cmd == "identify":
        from wellbeing_vision.identify import run_identify

        run_identify(settings, args.camera, args.seconds, args.rotate)
        return

    if args.cmd == "ambiente":
        from wellbeing_vision.ambiente import run_ambiente

        sink = Sink(settings.api_url, settings.outbox_path, dry_run=args.dry_run, dry_run_file=args.out)
        run_ambiente(settings, sink, args.cameras, args.window, args.rotate, args.seconds)
        return
    if args.astronaut not in settings.astronauts:
        parser.error(f"{args.astronaut} is not in the configured crew: {', '.join(settings.astronauts)}")
    if args.cmd == "enroll":
        from wellbeing_vision.identify import run_enroll

        if not run_enroll(settings, args.astronaut, args.camera, args.samples):
            raise SystemExit(1)
        return
    sink = Sink(settings.api_url, settings.outbox_path, dry_run=args.dry_run, dry_run_file=args.out)
    if args.cmd == "bitacora":
        from wellbeing_vision.bitacora import run_bitacora  # imports MediaPipe only when needed

        if run_bitacora(settings, sink, args.astronaut, args.camera, args.seconds, args.mirror, args.trace) is None:
            raise SystemExit(1)
