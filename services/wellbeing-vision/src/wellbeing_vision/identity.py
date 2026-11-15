"""Who is in front of the camera. YuNet finds faces, SFace turns each one into a 128-number template that is
compared with the enrolled crew. Templates stay in data/faces/ (local, gitignored): never sent, never images.

Rotation: YuNet only finds roughly upright faces, so the frame is also tried at 180/90/270 degrees. SFace
aligns every face by its eye line before the template, so an upside-down face matches an upright enrollment.
"""

import statistics
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from wellbeing_vision.schemas import Identity

ORIENTATIONS = (0, 180, 90, 270)
_ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
MATCH = 0.363  # SFace cosine threshold published with the model (OpenCV zoo); not tuned here
MARGIN = 0.08  # PROVISIONAL: the best astronaut must beat the runner-up by this much
AUTO_ENROLL = 0.5  # PROVISIONAL: only log frames that clearly match extend the gallery
AUTO_MAX = 20  # templates added by logs; the oldest go first. Enrolled ones are never dropped.
AUTO_PER_LOG = 3


def rotate(frame: np.ndarray, deg: int) -> np.ndarray:
    return frame if deg == 0 else cv2.rotate(frame, _ROTATE[deg])


def unrotate(pts: np.ndarray, deg: int, w: int, h: int) -> np.ndarray:
    """Map (x, y) points found in the frame rotated by deg back to the original w x h frame."""
    x, y = pts[..., 0], pts[..., 1]
    if deg == 0:
        return pts
    if deg == 180:
        out = (w - 1 - x, h - 1 - y)
    elif deg == 90:  # clockwise: original (x, y) -> rotated (h-1-y, x)
        out = (y, h - 1 - x)
    else:  # counter-clockwise: original (x, y) -> rotated (y, w-1-x)
        out = (w - 1 - y, x)
    return np.stack(out, axis=-1)


@dataclass
class Face:
    box: np.ndarray  # x0, y0, x1, y1 in frame pixels
    row: np.ndarray  # YuNet row (x, y, w, h, 5 landmarks, score) in frame pixels, for SFace alignment
    deg: int  # orientation it was found at

    @property
    def width(self) -> float:
        return float(min(self.box[2] - self.box[0], self.box[3] - self.box[1]))


class FaceID:
    def __init__(self, yunet: Path, sface: Path, min_score: float = 0.7) -> None:
        self.detector = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), min_score)
        self.recognizer = cv2.FaceRecognizerSF.create(str(sface), "")
        self.deg = 0  # sticky: the orientation that last found a face is tried first

    def detect(self, frame: np.ndarray, orientations=ORIENTATIONS) -> list[Face]:
        """Faces at the first orientation that finds any, starting with the last one that worked.
        shortcut: one orientation per frame, so an upright and an upside-down face are not seen together;
        run every orientation and merge by IoU if the demo needs mixed orientations."""
        h, w = frame.shape[:2]
        for deg in sorted(orientations, key=lambda d: d != self.deg):
            img = rotate(frame, deg)
            self.detector.setInputSize((img.shape[1], img.shape[0]))
            _, rows = self.detector.detect(img)
            if rows is not None:
                self.deg = deg
                return [_face(r, deg, w, h) for r in rows]
        return []

    def template(self, frame: np.ndarray, face: Face) -> np.ndarray:
        """Unit-length 128-number SFace template of one face (aligned by its landmarks)."""
        f = self.recognizer.feature(self.recognizer.alignCrop(frame, face.row)).ravel()
        return f / np.linalg.norm(f)


def _face(row: np.ndarray, deg: int, w: int, h: int) -> Face:
    x, y, fw, fh = row[:4]
    corners = unrotate(np.array([[x, y], [x + fw, y], [x, y + fh], [x + fw, y + fh]]), deg, w, h)
    (x0, y0), (x1, y1) = corners.min(axis=0), corners.max(axis=0)
    marks = unrotate(row[4:14].reshape(5, 2), deg, w, h)
    return Face(np.array([x0, y0, x1, y1]), np.array([x0, y0, x1 - x0, y1 - y0, *marks.ravel(), row[14]],
                                                     np.float32), deg)


class Gallery:
    """Templates per astronaut in data/faces/<id>.npz: 'enrolled' (enroll command) and 'auto' (verified logs)."""

    def __init__(self, faces_dir: Path) -> None:
        self.dir = faces_dir
        self.people: dict[str, dict[str, np.ndarray]] = {}

    def load(self, ids) -> "Gallery":
        for i in ids:
            path = self.dir / f"{i}.npz"
            if path.exists():
                with np.load(path) as z:
                    self.people[i] = {"enrolled": z["enrolled"], "auto": z["auto"]}
        return self

    def _save(self, astronaut_id: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        np.savez(self.dir / f"{astronaut_id}.npz", **self.people[astronaut_id])

    def enroll(self, astronaut_id: str, templates: list[np.ndarray]) -> None:
        """A new enrollment replaces the previous one, auto templates included."""
        self.people[astronaut_id] = {"enrolled": np.vstack(templates), "auto": np.empty((0, 128), np.float32)}
        self._save(astronaut_id)

    def add_auto(self, astronaut_id: str, templates: list[np.ndarray]) -> None:
        p = self.people[astronaut_id]
        p["auto"] = np.vstack([p["auto"], *templates])[-AUTO_MAX:]
        self._save(astronaut_id)

    def scores(self, template: np.ndarray) -> dict[str, float]:
        """Best cosine similarity against each astronaut's templates."""
        return {i: float(np.max(np.vstack([p["enrolled"], p["auto"]]) @ template)) for i, p in self.people.items()}


def best_match(scores: dict[str, float]) -> tuple[str | None, float]:
    """(astronaut, score) if the best is over MATCH and clearly ahead of the runner-up, else (None, score)."""
    if not scores:
        return None, 0.0
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    who, top = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else -1.0
    return (who if top >= MATCH and top - runner_up >= MARGIN else None), top


def verify(samples: list[tuple[dict[str, float], np.ndarray]], claimed: str) -> tuple[Identity, list[np.ndarray], str]:
    """Check a log's face samples (scores, template) against the claimed astronaut.
    Returns (identity for the payload, templates to add to the gallery, message)."""
    if not samples or not samples[0][0]:
        return Identity(method="manual"), [], "face check skipped: no enrolled faces or no face samples"
    if claimed not in samples[0][0]:
        return Identity(method="manual"), [], f"face check skipped: {claimed} is not enrolled"
    median = {i: statistics.median(s[i] for s, _ in samples) for i in samples[0][0]}
    who, score = best_match(median)
    if who != claimed:
        return Identity(method="manual"), [], (f"face does not confirm {claimed}: best {who or 'nobody'} "
                                               f"({score:.2f}); sent as manual")
    strong = sorted((s for s in samples if s[0][claimed] >= AUTO_ENROLL), key=lambda s: -s[0][claimed])
    add = [t for _, t in strong[:AUTO_PER_LOG]]
    return (Identity(method="face", match_score=round(min(max(median[claimed], 0.0), 1.0), 3)), add,
            f"face confirms {claimed} ({median[claimed]:.2f}); {len(add)} templates added to the gallery")
