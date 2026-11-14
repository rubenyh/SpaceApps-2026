"""Face metrics for the daily video log, measured as change against the neutral of the day.

Pure functions: landmarks/blendshapes in, numbers out. No camera here.
All thresholds are PROVISIONAL (no clinical source); they are relative to the person's own neutral.
"""

import math
import statistics
from dataclasses import dataclass, field

import numpy as np

from wellbeing_vision.schemas import Fatigue, Tension

# MediaPipe Face Mesh indices, ordered p1..p6 for the eye aspect ratio.
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)

EYE_CLOSED_RATIO = 0.6  # PROVISIONAL: eye closed when EAR < 60 % of the day's neutral EAR
EYE_REOPEN_RATIO = 0.7  # hysteresis: EAR jitter around 0.6 must not count as several blinks
YAWN_JAW_DELTA = 0.5  # PROVISIONAL: jawOpen blendshape above neutral
YAWN_MIN_S = 1.5  # PROVISIONAL: talking opens the jaw briefly; a yawn holds it
NOD_PITCH_DEG = 15.0  # PROVISIONAL: head dropped forward vs neutral
NOD_MIN_S = 0.3
MIN_VALID_S = 10.0  # below this, rates are not measurable -> None
MAX_DT_S = 0.2  # cap frame gaps so a stalled camera does not inflate durations


@dataclass
class FaceFrame:
    t: float
    ear: float
    jaw_open: float
    brow_down: float
    lip_press: float
    pitch: float


def eye_aspect_ratio(pts: np.ndarray) -> float:
    """pts: 6x2 pixel coords p1..p6. (|p2-p6| + |p3-p5|) / (2|p1-p4|)."""
    p1, p2, p3, p4, p5, p6 = pts
    width = np.linalg.norm(p1 - p4)
    if width == 0:
        return 0.0
    return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2 * width))


def pitch_degrees(matrix: np.ndarray) -> float:
    """Head pitch from MediaPipe's facial transformation matrix; positive = head down."""
    return math.degrees(math.atan2(matrix[2, 1], matrix[2, 2]))


def face_frame(t: float, landmarks, blendshapes, matrix, width: int, height: int) -> FaceFrame:
    """Build a FaceFrame from one MediaPipe FaceLandmarker face."""
    xy = np.array([(p.x * width, p.y * height) for p in landmarks])
    ear = (eye_aspect_ratio(xy[list(RIGHT_EYE)]) + eye_aspect_ratio(xy[list(LEFT_EYE)])) / 2
    bs = {c.category_name: c.score for c in blendshapes}
    return FaceFrame(
        t=t,
        ear=ear,
        jaw_open=bs["jawOpen"],
        brow_down=(bs["browDownLeft"] + bs["browDownRight"]) / 2,
        lip_press=(bs["mouthPressLeft"] + bs["mouthPressRight"]) / 2,
        pitch=pitch_degrees(np.asarray(matrix)),
    )


def neutral_of(frames: list[FaceFrame]) -> FaceFrame:
    """Median of the neutral window: robust to a blink during calibration."""
    med = lambda attr: statistics.median(getattr(f, attr) for f in frames)  # noqa: E731
    return FaceFrame(0.0, med("ear"), med("jaw_open"), med("brow_down"), med("lip_press"), med("pitch"))


@dataclass
class _Episode:
    """Counts episodes where a condition holds for at least min_s, once each."""

    min_s: float
    start: float | None = None
    counted: bool = False
    count: int = 0

    def update(self, active: bool, t: float) -> None:
        if not active:
            self.start, self.counted = None, False
            return
        if self.start is None:
            self.start = t
        if not self.counted and t - self.start >= self.min_s:
            self.count += 1
            self.counted = True


@dataclass
class SessionMetrics:
    neutral: FaceFrame
    frames_total: int = 0
    frames_valid: int = 0
    valid_s: float = 0.0
    closed_s: float = 0.0
    ear_ratio_sum: float = 0.0
    brow_delta_sum: float = 0.0
    lip_delta_sum: float = 0.0
    blinks: _Episode = field(default_factory=lambda: _Episode(0.0))
    yawns: _Episode = field(default_factory=lambda: _Episode(YAWN_MIN_S))
    nods: _Episode = field(default_factory=lambda: _Episode(NOD_MIN_S))
    eyes_closed: bool = False
    _last_t: float | None = None

    def add(self, frame: FaceFrame | None, t: float) -> None:
        """Feed every captured frame; None when no face was found."""
        self.frames_total += 1
        last, self._last_t = self._last_t, t
        if frame is None:
            return
        n = self.neutral
        dt = min(t - last, MAX_DT_S) if last is not None else 0.0
        limit = EYE_REOPEN_RATIO if self.eyes_closed else EYE_CLOSED_RATIO
        closed = self.eyes_closed = frame.ear < limit * n.ear
        self.frames_valid += 1
        self.valid_s += dt
        self.closed_s += dt if closed else 0.0
        self.ear_ratio_sum += frame.ear / n.ear if n.ear else 0.0
        # Only increases over the neutral count as tension (contract range 0-1).
        self.brow_delta_sum += max(0.0, frame.brow_down - n.brow_down)
        self.lip_delta_sum += max(0.0, frame.lip_press - n.lip_press)
        self.blinks.update(closed, t)
        self.yawns.update(frame.jaw_open - n.jaw_open > YAWN_JAW_DELTA, t)
        self.nods.update(frame.pitch - n.pitch > NOD_PITCH_DEG, t)

    @property
    def valid_frame_ratio(self) -> float:
        return self.frames_valid / self.frames_total if self.frames_total else 0.0

    def fatigue(self) -> Fatigue:
        if self.frames_valid == 0:
            return Fatigue(blink_rate_per_min=None, perclos=None, eye_openness_vs_neutral=None,
                           yawn_count=None, nod_count=None)
        enough = self.valid_s >= MIN_VALID_S
        return Fatigue(
            blink_rate_per_min=round(self.blinks.count / (self.valid_s / 60), 1) if enough else None,
            perclos=round(self.closed_s / self.valid_s, 3) if enough else None,
            eye_openness_vs_neutral=round(self.ear_ratio_sum / self.frames_valid, 3),
            yawn_count=self.yawns.count,
            nod_count=self.nods.count,
        )

    def tension(self) -> Tension:
        if self.frames_valid == 0:
            return Tension(brow_lower_delta=None, lip_press_delta=None)
        return Tension(
            brow_lower_delta=round(self.brow_delta_sum / self.frames_valid, 3),
            lip_press_delta=round(self.lip_delta_sum / self.frames_valid, 3),
        )
