"""Long-term neutral per astronaut: numbers only, in a local file under data/ (gitignored)."""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from wellbeing_vision.face import ANCHOR_MIN, ANCHOR_SESSIONS, FaceFrame, neutral_of


def anchor_file(data_dir: Path, astronaut_id: str) -> Path:
    return data_dir / "neutrals" / f"{astronaut_id}.jsonl"  # astronaut_id is pattern-checked by the CLI


def load_anchor(path: Path) -> tuple[FaceFrame | None, int]:
    """(median of the last ANCHOR_SESSIONS neutrals, how many were used). None below ANCHOR_MIN."""
    frames = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                frames.append(FaceFrame(0.0, **{k: v for k, v in row.items() if k != "at"}))
            except (ValueError, TypeError):  # a torn last line after a crash: skip it
                continue
    frames = frames[-ANCHOR_SESSIONS:]
    return (neutral_of(frames) if len(frames) >= ANCHOR_MIN else None), len(frames)


def save_neutral(path: Path, n: FaceFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now(UTC).isoformat()} | {k: round(v, 4) for k, v in asdict(n).items() if k != "t"}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
