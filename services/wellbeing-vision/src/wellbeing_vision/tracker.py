"""Person tracker: a track follows a face or a body, so someone who turns away keeps their track and name.

Each frame the poses are paired with the faces (the pose's nose inside the face box). A pose with visible
shoulders and no face is still a person (back or profile to the camera). Tracks are matched by face overlap
or body overlap, whichever is larger. Identity votes only come from frames where the face is seen.
"""

import itertools
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from wellbeing_vision.identity import Face, best_match
from wellbeing_vision.motion import NOSE, VISIBLE, body

IOU_MIN = 0.3
MAX_AGE = 15  # frames a track survives with neither its face nor its body
VOTES = 10  # identity is the mean over the last 10 templates of the track
MIN_VOTES = 3
EMBED_EVERY = 5  # frames between templates once a track has enough votes


def iou(a: np.ndarray, b: np.ndarray) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def body_box(pose: np.ndarray | None) -> np.ndarray | None:
    """Box around the visible pose landmarks, frame pixels."""
    if pose is None:
        return None
    pts = pose[pose[:, 2] > VISIBLE][:, :2]
    return np.array([*pts.min(axis=0), *pts.max(axis=0)]) if len(pts) >= 3 else None


@dataclass
class Track:
    id: int
    face: Face | None  # last face seen (may be old while the person looks away)
    last_seen: int
    votes: deque = field(default_factory=lambda: deque(maxlen=VOTES))  # score dicts, one per template
    last_template: int = -EMBED_EVERY
    pose: np.ndarray | None = None  # 33 x (x, y, visibility) in frame pixels, this frame
    body: np.ndarray | None = None  # last body box
    face_seen: int = -1  # frame index of the last detected face
    astronaut: str | None = None  # resolved by resolve(): unique across tracks
    score: float = 0.0

    def needs_template(self, frame_idx: int) -> bool:
        return self.face_seen == frame_idx and (
            len(self.votes) < MIN_VOTES or frame_idx - self.last_template >= EMBED_EVERY)

    def vote(self, scores: dict[str, float], frame_idx: int) -> None:
        self.votes.append(scores)
        self.last_template = frame_idx

    def candidate(self) -> tuple[str | None, float]:
        if len(self.votes) < MIN_VOTES or not self.votes[0]:
            return None, 0.0
        return best_match({i: float(np.mean([v[i] for v in self.votes])) for i in self.votes[0]})

    @property
    def box(self) -> np.ndarray:
        """Face box while the face is seen, else the body box: what the preview draws."""
        if self.face is not None and (self.face_seen == self.last_seen or self.body is None):
            return self.face.box
        return self.body

    @property
    def label(self) -> str:
        return self.astronaut or f"unknown-{self.id}"


def observations(faces: list[Face], poses: list[np.ndarray]) -> list[tuple[Face | None, np.ndarray | None]]:
    """People in one frame: each face with the pose whose nose is inside its box (grown by half, nearest
    first), then poses without a face if their shoulders are visible. A pose narrower than the face it
    would belong to is a misfire on the face itself (seen with no body in view) and is dropped."""
    used, out = set(), []
    for f in faces:
        x0, y0, x1, y1 = f.box
        gx, gy = (x1 - x0) / 2, (y1 - y0) / 2
        best, best_d = None, float("inf")
        for k, pose in enumerate(poses):
            nose = pose[NOSE]
            shoulders = float(np.hypot(*(pose[11][:2] - pose[12][:2])))
            if k in used or shoulders < x1 - x0 or not (x0 - gx <= nose[0] <= x1 + gx and y0 - gy <= nose[1] <= y1 + gy):
                continue
            d = float(np.hypot(nose[0] - (x0 + x1) / 2, nose[1] - (y0 + y1) / 2))
            if d < best_d:
                best, best_d = k, d
        if best is not None:
            used.add(best)
        out.append((f, poses[best] if best is not None else None))
    for k, pose in enumerate(poses):
        b = body(pose)
        if k in used or b is None:
            continue
        if any(b.sw < f.width and iou(body_box(pose), f.box) > 0 for f in faces):
            continue  # the misfire again: shoulders narrower than a face it overlaps is not a second person
        out.append((None, pose))
    return out


class IoUTracker:
    def __init__(self, ids=None) -> None:
        """ids: a shared counter, so tracks of several cameras never share an id (unknown-<id> stays unique)."""
        self.tracks: list[Track] = []
        self._ids = ids or itertools.count(1)

    def update(self, faces: list[Face], frame_idx: int, poses: list[np.ndarray] = ()) -> list[Track]:
        """Greedy association by face or body overlap. Returns the tracks seen in this frame."""
        obs = [(f, p, body_box(p)) for f, p in observations(faces, list(poses))]

        def overlap(t: Track, f: Face | None, bb: np.ndarray | None) -> float:
            s = iou(t.face.box, f.box) if f is not None and t.face is not None else 0.0
            return max(s, iou(t.body, bb) if bb is not None and t.body is not None else 0.0)

        pairs = sorted(((overlap(t, f, bb), ti, oi) for ti, t in enumerate(self.tracks)
                        for oi, (f, _, bb) in enumerate(obs)), key=lambda x: x[0], reverse=True)
        used_t, used_o, seen = set(), set(), []
        for score, ti, oi in pairs:
            if score < IOU_MIN:
                break
            if ti in used_t or oi in used_o:
                continue
            used_t.add(ti)
            used_o.add(oi)
            seen.append(self._apply(self.tracks[ti], *obs[oi], frame_idx))
        for oi, o in enumerate(obs):
            if oi not in used_o:
                t = self._apply(Track(next(self._ids), None, frame_idx), *o, frame_idx)
                self.tracks.append(t)
                seen.append(t)
        self.tracks = [t for t in self.tracks if frame_idx - t.last_seen <= MAX_AGE]
        return seen

    @staticmethod
    def _apply(t: Track, face: Face | None, pose: np.ndarray | None, bb: np.ndarray | None, frame_idx: int) -> Track:
        t.last_seen, t.pose = frame_idx, pose
        if face is not None:
            t.face, t.face_seen = face, frame_idx
        if bb is not None:
            t.body = bb
        return t


def resolve(tracks: list[Track]) -> None:
    """Give each track its astronaut; if two tracks claim the same one, the weaker becomes unknown."""
    claims = sorted(((t, *t.candidate()) for t in tracks), key=lambda c: -c[2])
    taken = set()
    for t, who, score in claims:
        t.score = score
        t.astronaut = who if who and who not in taken else None
        taken.add(who)
