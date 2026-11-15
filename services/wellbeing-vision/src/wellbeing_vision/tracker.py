"""IoU tracker for faces, identity votes per track, and pose skeletons linked to tracks by their boxes."""

import itertools
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from wellbeing_vision.identity import Face, best_match

IOU_MIN = 0.3
MAX_AGE = 15  # frames a track survives without a matching face
VOTES = 10  # identity is the mean over the last 10 templates of the track
MIN_VOTES = 3
EMBED_EVERY = 5  # frames between templates once a track has enough votes


def iou(a: np.ndarray, b: np.ndarray) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    id: int
    face: Face
    last_seen: int
    votes: deque = field(default_factory=lambda: deque(maxlen=VOTES))  # score dicts, one per template
    last_template: int = -EMBED_EVERY
    pose: np.ndarray | None = None  # 33 x (x, y, visibility) pose landmarks in frame pixels, if linked
    astronaut: str | None = None  # resolved by resolve(): unique across tracks
    score: float = 0.0

    def needs_template(self, frame_idx: int) -> bool:
        return len(self.votes) < MIN_VOTES or frame_idx - self.last_template >= EMBED_EVERY

    def vote(self, scores: dict[str, float], frame_idx: int) -> None:
        self.votes.append(scores)
        self.last_template = frame_idx

    def candidate(self) -> tuple[str | None, float]:
        if len(self.votes) < MIN_VOTES or not self.votes[0]:
            return None, 0.0
        return best_match({i: float(np.mean([v[i] for v in self.votes])) for i in self.votes[0]})

    @property
    def label(self) -> str:
        return self.astronaut or f"unknown-{self.id}"


class IoUTracker:
    def __init__(self, ids=None) -> None:
        """ids: a shared counter, so tracks of several cameras never share an id (unknown-<id> stays unique)."""
        self.tracks: list[Track] = []
        self._ids = ids or itertools.count(1)

    def update(self, faces: list[Face], frame_idx: int) -> list[Track]:
        """Greedy IoU association. Returns the tracks seen in this frame."""
        pairs = sorted(((iou(t.face.box, f.box), ti, fi) for ti, t in enumerate(self.tracks)
                        for fi, f in enumerate(faces)), reverse=True)
        used_t, used_f, seen = set(), set(), []
        for score, ti, fi in pairs:
            if score < IOU_MIN:
                break
            if ti in used_t or fi in used_f:
                continue
            used_t.add(ti)
            used_f.add(fi)
            t = self.tracks[ti]
            t.face, t.last_seen = faces[fi], frame_idx
            seen.append(t)
        for fi, f in enumerate(faces):
            if fi not in used_f:
                t = Track(next(self._ids), f, frame_idx)
                self.tracks.append(t)
                seen.append(t)
        self.tracks = [t for t in self.tracks if frame_idx - t.last_seen <= MAX_AGE]
        return seen


def resolve(tracks: list[Track]) -> None:
    """Give each track its astronaut; if two tracks claim the same one, the weaker becomes unknown."""
    claims = sorted(((t, *t.candidate()) for t in tracks), key=lambda c: -c[2])
    taken = set()
    for t, who, score in claims:
        t.score = score
        t.astronaut = who if who and who not in taken else None
        taken.add(who)


def link_poses(tracks: list[Track], poses: list[np.ndarray]) -> None:
    """Attach each pose to the track whose face box (grown by half) holds the pose's nose, nearest first.
    A pose whose shoulders are narrower than the face is a misfire on the face itself (seen with no body)."""
    for t in tracks:
        t.pose = None
    for pose in poses:
        nose, shoulders = pose[0], float(np.hypot(*(pose[11][:2] - pose[12][:2])))
        best, best_d = None, float("inf")
        for t in tracks:
            x0, y0, x1, y1 = t.face.box
            gx, gy = (x1 - x0) / 2, (y1 - y0) / 2
            if t.pose is None and shoulders >= x1 - x0 and x0 - gx <= nose[0] <= x1 + gx and y0 - gy <= nose[1] <= y1 + gy:
                d = float(np.hypot(nose[0] - (x0 + x1) / 2, nose[1] - (y0 + y1) / 2))
                if d < best_d:
                    best, best_d = t, d
        if best is not None:
            best.pose = pose
