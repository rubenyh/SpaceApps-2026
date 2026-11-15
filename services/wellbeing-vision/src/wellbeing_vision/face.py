"""Face metrics for the daily video log, measured as change against the neutral of the day.

Pure functions: landmarks/blendshapes in, numbers out. No camera here.
All thresholds are PROVISIONAL (no clinical source); they are relative to the person's own neutral.
"""

import math
import statistics
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from wellbeing_vision.schemas import Fatigue, Tension

# MediaPipe Face Mesh indices, ordered p1..p6 for the eye aspect ratio.
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)
FACE_EDGES = (234, 454)  # cheek to cheek: face width in pixels

# Eye closure uses the eyeBlink blendshape, not EAR: on the traced session they agree on 94 % of frames
# (r = -0.93), but EAR of open eyes doubles when the face moves away (1.1 -> 2.0 of neutral) and needs
# the day's neutral, while eyeBlink stays at 0.03-0.15 for open eyes at any distance.
EYE_BLINK_CLOSED = 0.4  # PROVISIONAL absolute bar
EYE_BLINK_OVER_NEUTRAL = 0.25  # PROVISIONAL: raised for someone whose open eyes already read high
EYE_BLINK_HYSTERESIS = 0.1  # reopen 0.1 below the bar: jitter must not count as several blinks
YAWN_JAW_DELTA = 0.35  # PROVISIONAL: jawOpen blendshape above neutral (0.5 missed acted yawns)
YAWN_MIN_S = 1.0  # PROVISIONAL: talking opens the jaw briefly; a yawn holds it
NOD_PITCH_DEG = 15.0  # PROVISIONAL: head dropped forward vs neutral
NOD_RETURN_DEG = 10.0  # hysteresis: a posture hovering around 15 degrees is not several nods
NOD_MIN_S = 0.3
NOD_MAX_S = 2.0  # PROVISIONAL: a nod drops and comes back; staying down longer is a posture (reading)
# Looking down (reading) lowers the lids and the brows: in the S3 trace the long low-lid stretches hold 87 %
# of the closed time and every brow (0.54-0.57) and lip (0.45) peak. Those frames are not comparable to a
# neutral taken at the camera. PROVISIONAL, eyeLookDown not traced yet.
GAZE_DOWN_DELTA = 0.25  # eyeLookDown blendshape over neutral (eyes down relative to the head)
GAZE_UP_DELTA = 0.2  # head down but eyes up over neutral: still looking at the camera
GAZE_DOWN_HOLD_S = 0.5  # longer than a blink, so a blink is never taken for looking down
DEEP_CLOSED_BLINK = 0.6  # a closure this deep counts even looking down (yawns and acted closures: 0.6-0.7)
TENSION_HOLD_S = 1.0  # a grimace must be held this long to count as a peak
# Talking presses the lips on every m/b/p, so lip press is measured only while the jaw is still.
# Jaw travel alone flagged single openings (a swallow, a sigh) as talking: 33 % of S3, 12 % of silent S1/S2.
SPEECH_JAW_OPEN = 0.03  # PROVISIONAL: jawOpen over neutral that counts as one opening
SPEECH_MIN_OPENINGS = 2  # talking opens the jaw again and again: 2 openings within SPEECH_WINDOW_S
SPEECH_WINDOW_S = 1.0  # on the S3 trace: 33 % talking -> 6 %
# Talking to the camera barely moves jawOpen (p90 0.003-0.01 in the R1-R3 traces), so mouthPress swings count
# too. A held press also moves, but with the lips above neutral: then the swings do not count.
# R1-R3 talking: 7/1/6 % -> 59/67/83 %; silent press L2: 0 % -> 0 %, its peak 0.466 kept.
SPEECH_LIP_SWING = 0.08  # PROVISIONAL: mouthPress reversal of at least this much
SPEECH_MIN_SWINGS = 2  # within SPEECH_WINDOW_S
SPEECH_PRESS_LEVEL = 0.1  # PROVISIONAL: lips this far over neutral (median of the window) = pressing
SPEECH_HANGOVER_S = 0.5  # lips close between words: keep excluding a moment after the jaw stops
MIN_VALID_S = 10.0  # below this, rates are not measurable -> None
MAX_DT_S = 0.2  # cap frame gaps so a stalled camera does not inflate durations

# Neutral calibration. PROVISIONAL, tuned on one person's traces.
CALIB_BLINK_JUMP = 0.15  # eyeBlink off the window median: a blink or squint
CALIB_MOVE_DEG = 5.0  # head pitch or yaw off the window median
CALIB_JAW_JUMP = 0.10  # talking or moving the mouth
CALIB_GAZE_JUMP = 0.15  # eyeLookDown off the window median: looking away from the camera
NEUTRAL_MAX_BLINK = 0.3  # real neutrals at the camera read 0.20-0.24; squinting or reading 0.3-0.45
ANCHOR_SESSIONS = 7  # anchor = median of the last 7 neutrals: one bad day cannot move it, a slow drift can
ANCHOR_MIN = 3
ANCHOR_EAR_DEV = 0.15  # today's neutral EAR this far from the anchor is suspicious


@dataclass
class FaceFrame:
    t: float
    ear: float
    jaw_open: float
    brow_down: float
    lip_press: float
    pitch: float
    face_px: float = 0.0
    eye_blink: float = 0.0  # MediaPipe eyeBlink blendshape, 0 open .. 1 closed
    yaw: float = 0.0
    look_down: float = 0.0  # eyeLookDown blendshape: eyes down relative to the head
    look_up: float = 0.0


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


def yaw_degrees(matrix: np.ndarray) -> float:
    return math.degrees(math.atan2(-matrix[2, 0], math.hypot(matrix[2, 1], matrix[2, 2])))


def face_frame(t: float, xy: np.ndarray, blendshapes, matrix) -> FaceFrame:
    """Build a FaceFrame from one face: xy are landmark pixel coords in the original frame."""
    ear = (eye_aspect_ratio(xy[list(RIGHT_EYE)]) + eye_aspect_ratio(xy[list(LEFT_EYE)])) / 2
    bs = {c.category_name: c.score for c in blendshapes}
    matrix = np.asarray(matrix)
    return FaceFrame(
        t=t,
        ear=ear,
        jaw_open=bs["jawOpen"],
        brow_down=(bs["browDownLeft"] + bs["browDownRight"]) / 2,
        lip_press=(bs["mouthPressLeft"] + bs["mouthPressRight"]) / 2,
        pitch=pitch_degrees(matrix),
        face_px=float(np.linalg.norm(xy[FACE_EDGES[0]] - xy[FACE_EDGES[1]])),
        eye_blink=(bs["eyeBlinkLeft"] + bs["eyeBlinkRight"]) / 2,
        yaw=yaw_degrees(matrix),
        look_down=(bs["eyeLookDownLeft"] + bs["eyeLookDownRight"]) / 2,
        look_up=(bs["eyeLookUpLeft"] + bs["eyeLookUpRight"]) / 2,
    )


def neutral_of(frames: list[FaceFrame]) -> FaceFrame:
    """Median of the neutral window: robust to a blink during calibration."""
    return FaceFrame(0.0, **{k: statistics.median(getattr(f, k) for f in frames)
                             for k in FaceFrame.__dataclass_fields__ if k != "t"})


def calibration_break(window: list[FaceFrame], f: FaceFrame) -> str | None:
    """Why f breaks a steady neutral window: 'blink', 'move', 'mouth' or 'gaze'. None = still steady."""
    if not window:
        return None
    med = lambda attr: statistics.median(getattr(x, attr) for x in window)  # noqa: E731
    if abs(f.eye_blink - med("eye_blink")) > CALIB_BLINK_JUMP:
        return "blink"
    if max(abs(f.pitch - med("pitch")), abs(f.yaw - med("yaw"))) > CALIB_MOVE_DEG:
        return "move"
    if abs(f.jaw_open - med("jaw_open")) > CALIB_JAW_JUMP:
        return "mouth"
    if abs(f.look_down - med("look_down")) > CALIB_GAZE_JUMP:
        return "gaze"
    return None


def neutral_problem(n: FaceFrame, anchor: FaceFrame | None) -> str | None:
    """'squint' if the eyes are not plausibly open, 'anchor' if EAR is far from the usual neutral."""
    limit = NEUTRAL_MAX_BLINK if anchor is None else max(NEUTRAL_MAX_BLINK, anchor.eye_blink + CALIB_BLINK_JUMP)
    if n.eye_blink > limit:
        return "squint"
    if anchor is not None and abs(n.ear / anchor.ear - 1) > ANCHOR_EAR_DEV:
        return "anchor"
    return None


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
class _SustainedPeak:
    """Highest level held for at least hold_s: max over time of the rolling minimum.
    A 1.5 s frown in a 60 s log is ~2 % of frames, so a mean or a p90 would both miss it."""

    hold_s: float
    window: deque = field(default_factory=deque)
    peak: float | None = None

    def update(self, value: float | None, t: float) -> None:
        if value is None:  # the hold must be continuous
            self.window.clear()
            return
        self.window.append((t, value))
        while len(self.window) > 1 and self.window[1][0] <= t - self.hold_s:
            self.window.popleft()
        if self.window[0][0] <= t - self.hold_s:
            level = min(v for _, v in self.window)
            self.peak = level if self.peak is None else max(self.peak, level)


@dataclass
class _Speech:
    """Talking moves the mouth again and again: jaw openings, or mouthPress swinging below a held press.
    One opening or one swing (a swallow, a sigh, starting a press) is not talking."""

    rises: deque = field(default_factory=deque)
    armed: bool = True
    swings: deque = field(default_factory=deque)
    lips: deque = field(default_factory=deque)
    extreme: float | None = None
    direction: int = 0
    until: float = -math.inf

    def update(self, jaw_delta: float | None, lip_delta: float | None, t: float) -> bool:
        if jaw_delta is None or lip_delta is None:
            self.rises.clear()
            self.swings.clear()
            self.lips.clear()
            self.armed, self.extreme, self.direction = True, None, 0
            return False
        if self.armed and jaw_delta > SPEECH_JAW_OPEN:
            self.rises.append(t)
            self.armed = False
        elif jaw_delta < SPEECH_JAW_OPEN / 2:  # closed again: the next opening counts
            self.armed = True
        if self.extreme is None:
            self.extreme = lip_delta
        elif self.direction >= 0 and lip_delta > self.extreme:
            self.extreme, self.direction = lip_delta, 1
        elif self.direction <= 0 and lip_delta < self.extreme:
            self.extreme, self.direction = lip_delta, -1
        elif abs(lip_delta - self.extreme) >= SPEECH_LIP_SWING:  # turned back by a full swing
            self.swings.append(t)
            self.extreme, self.direction = lip_delta, -self.direction
        self.lips.append((t, lip_delta))
        for q in (self.rises, self.swings):
            while q and q[0] < t - SPEECH_WINDOW_S:
                q.popleft()
        while self.lips[0][0] < t - SPEECH_WINDOW_S:
            self.lips.popleft()
        pressing = statistics.median(v for _, v in self.lips) >= SPEECH_PRESS_LEVEL
        if len(self.rises) >= SPEECH_MIN_OPENINGS or (len(self.swings) >= SPEECH_MIN_SWINGS and not pressing):
            self.until = t + SPEECH_HANGOVER_S
        return t <= self.until


@dataclass
class _Dip:
    """A nod: the head drops past NOD_PITCH_DEG and comes back under NOD_RETURN_DEG within
    NOD_MIN_S..NOD_MAX_S. Staying down longer is a posture (reading), not a nod."""

    start: float | None = None
    count: int = 0

    def update(self, drop_deg: float, t: float) -> None:
        if self.start is None:
            if drop_deg > NOD_PITCH_DEG:
                self.start = t
        elif drop_deg < NOD_RETURN_DEG:
            self.count += NOD_MIN_S <= t - self.start <= NOD_MAX_S
            self.start = None


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
    lip_frames: int = 0
    quiet_s: float = 0.0  # valid time without talking: the only time lip press is measured
    talking_s: float = 0.0
    speaking: bool = False
    blinks: _Episode = field(default_factory=lambda: _Episode(0.0))
    yawns: _Episode = field(default_factory=lambda: _Episode(YAWN_MIN_S))
    nods: _Dip = field(default_factory=_Dip)
    brow_peak: _SustainedPeak = field(default_factory=lambda: _SustainedPeak(TENSION_HOLD_S))
    lip_peak: _SustainedPeak = field(default_factory=lambda: _SustainedPeak(TENSION_HOLD_S))
    speech: _Speech = field(default_factory=_Speech)
    eyes_closed: bool = False
    down_since: float | None = None
    looking_down: bool = False  # held for GAZE_DOWN_HOLD_S: the preview asks to look at the camera
    # PERCLOS time (valid s, closed s) while looking down is not decided yet: kept if the gaze comes back
    # before GAZE_DOWN_HOLD_S (a blink, a glance), dropped if it turns out to be looking down.
    _pending: list = field(default_factory=lambda: [0.0, 0.0])
    _last_t: float | None = None

    def _settle(self, keep: bool) -> None:
        if keep:
            self.valid_s += self._pending[0]
            self.closed_s += self._pending[1]
        self._pending = [0.0, 0.0]

    def add(self, frame: FaceFrame | None, t: float) -> None:
        """Feed every captured frame; None when no face was found."""
        self.frames_total += 1
        last, self._last_t = self._last_t, t
        n = self.neutral
        if frame is not None:
            self.nods.update(frame.pitch - n.pitch, t)  # every face: a nod ends where looking down begins
            down = frame.look_down - n.look_down > GAZE_DOWN_DELTA or (
                frame.pitch - n.pitch > NOD_PITCH_DEG and frame.look_up - n.look_up < GAZE_UP_DELTA)
            self.down_since = (t if self.down_since is None else self.down_since) if down else None
            self.looking_down = down and t - self.down_since >= GAZE_DOWN_HOLD_S
            if not down or self.looking_down:
                self._settle(keep=not down)
            if self.looking_down and frame.eye_blink < DEEP_CLOSED_BLINK:
                frame = None  # lowered lids and brows of reading, not fatigue or tension
        else:
            self.down_since, self.looking_down = None, False
            self._settle(keep=True)
        if frame is None:
            self.brow_peak.update(None, t)
            self.lip_peak.update(None, t)
            self.speaking = self.speech.update(None, None, t)
            return
        dt = min(t - last, MAX_DT_S) if last is not None else 0.0
        bar = max(EYE_BLINK_CLOSED, n.eye_blink + EYE_BLINK_OVER_NEUTRAL)
        closed = self.eyes_closed = frame.eye_blink > (bar - EYE_BLINK_HYSTERESIS if self.eyes_closed else bar)
        self.frames_valid += 1
        undecided = self.down_since is not None and not self.looking_down and frame.eye_blink < DEEP_CLOSED_BLINK
        if undecided:
            self._pending[0] += dt
            self._pending[1] += dt if closed else 0.0
        else:
            self.valid_s += dt
            self.closed_s += dt if closed else 0.0
        self.ear_ratio_sum += frame.ear / n.ear if n.ear else 0.0
        # Only increases over the neutral count as tension (contract range 0-1).
        brow, lip = max(0.0, frame.brow_down - n.brow_down), max(0.0, frame.lip_press - n.lip_press)
        self.brow_delta_sum += brow
        self.brow_peak.update(brow, t)
        self.speaking = self.speech.update(frame.jaw_open - n.jaw_open, frame.lip_press - n.lip_press, t)
        self.lip_peak.update(None if self.speaking else lip, t)
        if not self.speaking:
            self.lip_delta_sum += lip
            self.lip_frames += 1
            self.quiet_s += dt
        else:
            self.talking_s += dt
        self.blinks.update(closed, t)
        self.yawns.update(frame.jaw_open - n.jaw_open > YAWN_JAW_DELTA, t)

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
        r = lambda v: None if v is None else round(v, 3)  # noqa: E731
        lip_ok = self.quiet_s >= MIN_VALID_S  # mostly talking: lip press is not measurable
        return Tension(
            brow_lower_delta=round(self.brow_delta_sum / self.frames_valid, 3),
            lip_press_delta=round(self.lip_delta_sum / self.lip_frames, 3) if lip_ok else None,
            brow_lower_peak_1s=r(self.brow_peak.peak),
            lip_press_peak_1s=r(self.lip_peak.peak) if lip_ok else None,
        )
