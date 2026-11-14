import argparse

from wellbeing_vision.config import Settings
from wellbeing_vision.download import download_models


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(prog="wellbeing-vision")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models", help="download model files into models_dir")

    args = parser.parse_args()
    if args.cmd == "models":
        download_models(settings.models_dir)
