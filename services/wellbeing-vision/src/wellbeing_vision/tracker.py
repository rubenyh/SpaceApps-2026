"""Person tracker: a track follows a face or a body, so someone who turns away keeps their track and name.

Each frame the poses are paired with the faces (the pose's nose inside the face box). A pose with visible
shoulders and no face is still a person (back or profile to the camera). Tracks are matched by overlap or by
centre distance after a constant-velocity prediction, so a low frame rate does not split one person into many
tracks. Lost tracks wait MAX_AGE_S; an unknown that comes back in the same place gets its old track back.
Identity votes only come from frames where the face is seen. All times are seconds.
"""

import itertools
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from wellbeing_vision.identity import Face, best_match
from wellbeing_vision.motion import NOSE, VISIBLE, body

MATCH_MIN = 0.1  # PROVISIONAL: overlap, or closeness of centres, needed to continue a track
CENTER_GATE = 1.0  # centres within 1 box width (after prediction) count as the same person
MAX_AGE_S = 2.0  # a track survives this long with neither its face nor its body
REVIVE_S = 10.0  # an unknown seen again in the same place within this time keeps its old track
MIN_LIFE_S = 3.0  # PROVISIONAL: younger tracks are shown but not counted as occupants or pairs
MIN_FACE_PX = 24  # smaller faces are mostly false detections
FACE_ONLY_SCORE = 0.85  # a face with no body needs a more confident detection
VOTES = 10  # identity is the mean over the last 10 templates of the track
MIN_VOTES = 3
REVERIFY_S = 2.0  # an identified track is checked again every 2 s
UNKNOWN_RETRY_S = 1.0  # an unknown track tries again every second


def iou(a: np.ndarray, b: np.ndarray) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _center(box: np.ndarray) -> np.ndarray:
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])


def similarity(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """max(IoU, closeness of centres): 1 at the same place, 0 from CENTER_GATE box widths apart."""
    if a is None or b is None:
        return 0.0
    size = max(a[2] - a[0], b[2] - b[0], 1.0)
    close = 1.0 - float(np.linalg.norm(_center(a) - _center(b))) / (CENTER_GATE * size)
    return max(iou(a, b), close)


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
    last_seen: float
    votes: deque = field(default_factory=lambda: deque(maxlen=VOTES))  # score dicts, one per template
    last_template: float = -1e9
    pose: np.ndarray | None = None  # 33 x (x, y, visibility) in frame pixels, this frame
    body: np.ndarray | None = None  # last body box
    face_seen: float = -1e9  # time of the last detected face
    born: float | None = None
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))  # px/s of the box centre
    astronaut: str | None = None  # resolved by resolve(): unique within a camera
    score: float = 0.0
    elsewhere: str | None = None  # set by the ambient loop: same astronaut, counted in that module

    def __post_init__(self) -> None:
        if self.born is None:
            self.born = self.last_seen

    def needs_template(self, t: float) -> bool:
        if self.face_seen != t:
            return False
        if len(self.votes) < MIN_VOTES:
            return True
        return t - self.last_template >= (REVERIFY_S if self.astronaut else UNKNOWN_RETRY_S)

    def vote(self, scores: dict[str, float], t: float) -> None:
        self.votes.append(scores)
        self.last_template = t

    def candidate(self) -> tuple[str | None, float]:
        if len(self.votes) < MIN_VOTES or not self.votes[0]:
            return None, 0.0
        return best_match({i: float(np.mean([v[i] for v in self.votes])) for i in self.votes[0]})

    def mature(self, t: float, min_life_s: float = MIN_LIFE_S) -> bool:
        return t - self.born >= min_life_s

    def predicted(self, box: np.ndarray | None, t: float) -> np.ndarray | None:
        """box moved by the track's velocity to time t (at most one box width)."""
        if box is None:
            return None
        shift = self.velocity * (t - self.last_seen)
        width = box[2] - box[0]
        shift *= min(1.0, width / max(float(np.linalg.norm(shift)), 1e-9))
        return box + np.array([*shift, *shift])

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
    first), then poses without a face if their shoulders are visible. Tiny faces, and faces with no body
    unless confidently detected, are dropped as false detections. A pose narrower than the face it would
    belong to is a misfire on the face itself (seen with no body in view) and is dropped."""
    used, out = set(), []
    for f in faces:
        if f.width < MIN_FACE_PX:
            continue
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
        elif f.row[14] < FACE_ONLY_SCORE:
            continue
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
        self.lost: list[Track] = []  # recently ended unknown tracks, for REVIVE_S
        self._ids = ids or itertools.count(1)

    def update(self, faces: list[Face], t: float, poses: list[np.ndarray] = ()) -> list[Track]:
        """Greedy association by face or body similarity after prediction. Returns the tracks seen at t."""
        obs = [(f, p, body_box(p)) for f, p in observations(faces, list(poses))]

        def match(tr: Track, f: Face | None, bb: np.ndarray | None, now: float) -> float:
            return max(similarity(tr.predicted(tr.face.box, now) if tr.face is not None else None,
                                  f.box if f is not None else None),
                       similarity(tr.predicted(tr.body, now), bb))

        pairs = sorted(((match(tr, f, bb, t), ti, oi) for ti, tr in enumerate(self.tracks)
                        for oi, (f, _, bb) in enumerate(obs)), key=lambda x: x[0], reverse=True)
        used_t, used_o, seen = set(), set(), []
        for score, ti, oi in pairs:
            if score < MATCH_MIN:
                break
            if ti in used_t or oi in used_o:
                continue
            used_t.add(ti)
            used_o.add(oi)
            seen.append(self._apply(self.tracks[ti], *obs[oi], t))
        self.lost = [tr for tr in self.lost if t - tr.last_seen <= REVIVE_S]
        for oi, (f, p, bb) in enumerate(obs):
            if oi in used_o:
                continue
            back = max(self.lost, key=lambda tr: match(tr, f, bb, tr.last_seen), default=None)
            if back is not None and match(back, f, bb, back.last_seen) >= MATCH_MIN:
                self.lost.remove(back)  # the same unknown, back in the same place
                tr = back
            else:
                tr = Track(next(self._ids), None, t)
            self.tracks.append(self._apply(tr, f, p, bb, t))
            seen.append(tr)
        ended = [tr for tr in self.tracks if t - tr.last_seen > MAX_AGE_S]
        self.lost += [tr for tr in ended if tr.astronaut is None]
        self.tracks = [tr for tr in self.tracks if t - tr.last_seen <= MAX_AGE_S]
        return seen

    @staticmethod
    def _apply(tr: Track, face: Face | None, pose: np.ndarray | None, bb: np.ndarray | None, t: float) -> Track:
        # Velocity from the same kind of box as before: face to face, else body to body.
        old, new = (tr.face.box, face.box) if face is not None and tr.face is not None else (tr.body, bb)
        if old is not None and new is not None and t > tr.last_seen:
            tr.velocity = 0.5 * tr.velocity + 0.5 * (_center(new) - _center(old)) / (t - tr.last_seen)
        tr.last_seen, tr.pose = t, pose
        if face is not None:
            tr.face, tr.face_seen = face, t
        if bb is not None:
            tr.body = bb
        return tr


def resolve(tracks: list[Track]) -> None:
    """Give each track its astronaut; if two tracks claim the same one, the weaker becomes unknown."""
    claims = sorted(((tr, *tr.candidate()) for tr in tracks), key=lambda c: -c[2])
    taken = set()
    for tr, who, score in claims:
        tr.score = score
        tr.astronaut = who if who and who not in taken else None
        taken.add(who)
