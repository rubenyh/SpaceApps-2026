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
    amb.add_argument("--overlap", action="store_true",
                     help="the cameras watch the same space: count them as one module (default: one zone each)")
    amb.add_argument("--size", default=f"{settings.ambient_width}x{settings.ambient_height}",
                     help="capture size WxH (default 640x480; the daily log always asks 1280x720)")
    amb.add_argument("--min-track", type=float, default=settings.min_track_s,
                     help="seconds a track must live before it counts as occupant or in pairs")
    amb.add_argument("--trace", type=Path, help="CSV per frame and track (no images) for tuning")
    amb.add_argument("--dry-run", action="store_true", help="print JSON instead of POSTing")
    amb.add_argument("--out", type=Path, help="with --dry-run, also append JSON lines here")

    for p in (bit, enr, ide, amb):
        p.add_argument("--backend", choices=("auto", "dshow", "msmf"),
                       help="camera backend (default WELLBEING_VISION_CAMERA_BACKEND or auto: DSHOW, then MSMF)")
        p.add_argument("--flip", type=int, nargs="+", metavar="CAM",
                       help="mirror these cameras before processing and display (e.g. a phone webcam: --flip 1)")
        p.add_argument("--turn", nargs="+", metavar="CAM:DEG",
                       help="turn these cameras clockwise before processing and display, e.g. --turn 1:180")

    args = parser.parse_args()
    if getattr(args, "backend", None):
        settings = settings.model_copy(update={"camera_backend": args.backend})
    if getattr(args, "flip", None):
        settings = settings.model_copy(update={"camera_flip": args.flip})
    if getattr(args, "turn", None):
        try:
            turns = {int(c): int(d) for c, d in (x.split(":") for x in args.turn)}
        except ValueError:
            parser.error("--turn takes CAM:DEG, e.g. 1:180")
        if any(d not in (0, 90, 180, 270) for d in turns.values()):
            parser.error("--turn degrees must be 0, 90, 180 or 270")
        settings = settings.model_copy(update={"camera_turn": turns})
    if args.cmd == "models":
        download_models(settings.models_dir)
        return
    if args.cmd == "identify":
        from wellbeing_vision.identify import run_identify

        run_identify(settings, args.camera, args.seconds, args.rotate)
        return

    if args.cmd == "ambiente":
        from wellbeing_vision.ambiente import run_ambiente

        try:
            w, h = (int(v) for v in args.size.lower().split("x"))
        except ValueError:
            parser.error("--size takes WxH, e.g. 640x480")
        settings = settings.model_copy(update={"ambient_width": w, "ambient_height": h, "min_track_s": args.min_track})
        sink = Sink(settings.api_url, settings.outbox_path, dry_run=args.dry_run, dry_run_file=args.out)
        run_ambiente(settings, sink, args.cameras, args.window, args.rotate, args.seconds, args.overlap, args.trace)
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
