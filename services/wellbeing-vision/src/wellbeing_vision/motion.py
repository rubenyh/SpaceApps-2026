"""Ambient mode metrics for one module window: who was there, who shared the space, and how they moved.

Pure: pose landmarks (33 x (x, y, visibility) in frame pixels) in, contract payloads out. Every measure is
relative to the body (shoulder widths, angles against the shoulder line), so an upside-down camera or an
astronaut floating at any angle gives the same numbers. All thresholds are PROVISIONAL.
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations

import numpy as np

from wellbeing_vision.schemas import (
    CoPresence, CoPresenceOccupant, CoPresencePair, Identity, Motion, VisionSession, quality_of,
)

L_SHOULDER, R_SHOULDER, NOSE = 11, 12, 0
WRISTS = (15, 16)
VISIBLE = 0.5
STATIONARY_SW_S = 0.1  # PROVISIONAL: torso slower than 0.1 shoulder widths/s counts as still
JUMP_SW_S = 5.0  # PROVISIONAL: faster is a tracking jump (track swapped or re-found), not movement
FACING_TURN = 0.15  # PROVISIONAL: nose this far (shoulder widths) toward the other person = facing them
MIN_PRESENT_S = 1.0  # less than this in a window is a detection blip, not an occupant
MIN_POSE_S = 10.0  # motion needs this much pose time in the window, else no ambient session


@dataclass
class Body:
    mid: np.ndarray  # shoulder midpoint, pixels
    sw: float  # shoulder width, pixels
    along: np.ndarray  # unit vector left -> right shoulder
    angle: float  # head against the torso: neck vs the shoulder-line normal, degrees
    turn: float  # nose offset along the shoulder line, shoulder widths (head turned that way)


def body(pose: np.ndarray | None) -> Body | None:
    if pose is None or min(pose[L_SHOULDER][2], pose[R_SHOULDER][2]) < VISIBLE:
        return None
    axis = pose[R_SHOULDER][:2] - pose[L_SHOULDER][:2]
    sw = float(np.linalg.norm(axis))
    if sw < 1.0:
        return None
    mid = (pose[L_SHOULDER][:2] + pose[R_SHOULDER][:2]) / 2
    along = axis / sw
    normal = np.array([along[1], -along[0]])
    neck = pose[NOSE][:2] - mid
    if neck @ normal < 0:  # the normal that points at the head, whatever the camera orientation
        normal = -normal
    return Body(mid, sw, along, math.degrees(math.atan2(neck @ along, neck @ normal)), float(neck @ along / sw))


def facing(a: Body, b: Body) -> bool:
    """a's head is turned toward b (2D, from the camera's view)."""
    return a.turn * float((b.mid - a.mid) @ a.along) > 0 and abs(a.turn) >= FACING_TURN


@dataclass
class PersonWindow:
    present_s: float = 0.0
    frames: int = 0
    pose_frames: int = 0
    pose_s: float = 0.0
    still_s: float = 0.0
    travel_sw: float = 0.0  # torso path, shoulder widths
    fidget_sw: float = 0.0  # wrist path relative to the torso, shoulder widths
    fidget_s: float = 0.0
    angles: list = field(default_factory=list)
    _last: tuple | None = None

    def add(self, dt: float, pose: np.ndarray | None, b: Body | None) -> None:
        self.present_s += dt
        self.frames += 1
        if b is None:
            self._last = None
            return
        self.pose_frames += 1
        wrists = {i: (pose[i][:2] - b.mid) / b.sw for i in WRISTS if pose[i][2] >= VISIBLE}
        if self._last is not None and dt > 0:
            prev, prev_wrists = self._last
            speed = float(np.linalg.norm(b.mid - prev.mid)) / ((b.sw + prev.sw) / 2) / dt
            if speed > JUMP_SW_S:
                self._last = (b, wrists)
                return
            self.pose_s += dt
            self.travel_sw += speed * dt
            self.still_s += dt if speed < STATIONARY_SW_S else 0.0
            common = wrists.keys() & prev_wrists.keys()
            if common:
                self.fidget_sw += float(np.mean([np.linalg.norm(wrists[i] - prev_wrists[i]) for i in common]))
                self.fidget_s += dt
        self.angles.append(b.angle)
        self._last = (b, wrists)

    def merge(self, o: "PersonWindow") -> "PersonWindow":
        """Two tracks of the same person in one window (lost and found again)."""
        return PersonWindow(self.present_s + o.present_s, self.frames + o.frames, self.pose_frames + o.pose_frames,
                            self.pose_s + o.pose_s, self.still_s + o.still_s, self.travel_sw + o.travel_sw,
                            self.fidget_sw + o.fidget_sw, self.fidget_s + o.fidget_s, self.angles + o.angles)

    def motion(self) -> Motion | None:
        if self.pose_s < MIN_POSE_S:
            return None
        med = statistics.median(self.angles)
        return Motion(
            speed=round(self.travel_sw / self.pose_s, 3),
            stationary_ratio=round(self.still_s / self.pose_s, 3),
            fidget_index=round(self.fidget_sw / self.fidget_s, 3) if self.fidget_s else None,
            torso_angle_dev=round(statistics.fmean(abs(a - med) for a in self.angles), 1),
        )


@dataclass
class PairWindow:
    together_s: float = 0.0
    posed_s: float = 0.0  # together with both poses: distance and facing are measured on this time
    distance_sw: float = 0.0  # integral of the distance, shoulder widths x s
    facing_s: float = 0.0


class ModuleWindow:
    """One module (camera) over one window. Tracks are keyed by track id; labels are applied at flush."""

    def __init__(self, module_id: str, source: str, start: datetime) -> None:
        self.module_id, self.source, self.start = module_id, source, start
        self.people: dict[int, PersonWindow] = {}
        self.pairs: dict[tuple[int, int], PairWindow] = {}
        self.covered_s = 0.0

    def add(self, dt: float, people: dict[int, np.ndarray | None]) -> None:
        """One processed frame: the tracks in view and their poses (None if no pose was linked)."""
        self.covered_s += dt
        bodies = {tid: body(pose) for tid, pose in people.items()}
        for tid, pose in people.items():
            self.people.setdefault(tid, PersonWindow()).add(dt, pose, bodies[tid])
        for a, b in combinations(sorted(people), 2):
            p = self.pairs.setdefault((a, b), PairWindow())
            p.together_s += dt
            ba, bb = bodies[a], bodies[b]
            if ba and bb:
                p.posed_s += dt
                p.distance_sw += float(np.linalg.norm(ba.mid - bb.mid)) / ((ba.sw + bb.sw) / 2) * dt
                p.facing_s += dt if facing(ba, bb) and facing(bb, ba) else 0.0

    def present(self, labels: dict[int, str]) -> dict[str, float]:
        """Seconds present so far per label (for the preview)."""
        out: dict[str, float] = {}
        for tid, pw in self.people.items():
            label = labels.get(tid, f"unknown-{tid}")
            out[label] = out.get(label, 0.0) + pw.present_s
        return out

    def flush(self, labels: dict[int, str], scores: dict[str, float],
              end: datetime) -> tuple[CoPresence | None, list[VisionSession]]:
        """Contract payloads for this window: one co-presence record and one ambient session per person."""
        length = (end - self.start).total_seconds()
        label = lambda tid: labels.get(tid, f"unknown-{tid}")  # noqa: E731
        people: dict[str, PersonWindow] = {}
        for tid, pw in self.people.items():
            people[label(tid)] = people[label(tid)].merge(pw) if label(tid) in people else pw
        people = {k: v for k, v in people.items() if v.present_s >= MIN_PRESENT_S}
        pairs: dict[tuple[str, str], PairWindow] = {}
        for (ta, tb), p in self.pairs.items():
            a, b = sorted((label(ta), label(tb)))
            if a == b or a not in people or b not in people:
                continue
            q = pairs.setdefault((a, b), PairWindow())
            q.together_s += p.together_s
            q.posed_s += p.posed_s
            q.distance_sw += p.distance_sw
            q.facing_s += p.facing_s
        co = CoPresence(
            module_id=self.module_id, source=self.source, window_start=self.start, window_end=end,
            occupants=[CoPresenceOccupant(astronaut_id=k, seconds_present=round(min(v.present_s, length), 1))
                       for k, v in people.items()],
            pairs=[CoPresencePair(a=a, b=b, seconds_together=round(min(p.together_s, length), 1),
                                  mean_distance_shoulders=round(p.distance_sw / p.posed_s, 2) if p.posed_s else None,
                                  facing_ratio=round(p.facing_s / p.posed_s, 3) if p.posed_s else None)
                   for (a, b), p in pairs.items()],
            quality=quality_of(min(self.covered_s / length, 1.0)) if length > 0 else "bad",
        ) if people else None
        sessions = []
        for k, pw in people.items():
            m = pw.motion()
            if m is None:
                continue
            ratio = pw.pose_frames / pw.frames
            score = scores.get(k)
            sessions.append(VisionSession(
                astronaut_id=k, session_type="ambiente", module_id=self.module_id, source=self.source,
                started_at=self.start, ended_at=end, quality=quality_of(ratio), valid_frame_ratio=round(ratio, 3),
                identity=Identity(method="face", match_score=None if score is None else round(min(max(score, 0.0), 1.0), 3)),
                neutral_ok=False,  # ambient mode has no facial neutral; only motion is sent
                fatigue=None, tension=None, motion=m,
            ))
        return co, sessions
