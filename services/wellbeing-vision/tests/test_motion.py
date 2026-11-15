import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from wellbeing_vision.motion import ModuleWindow, body, facing

START = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
FPS = 10


def pose(cx, cy, sw=100.0, turn=0.0, wrist=(0.0, 0.0), deg=0.0):
    """Upright torso at (cx, cy), head turned `turn` shoulder widths, rotated deg about the torso."""
    pts = np.zeros((33, 3))
    local = {11: (-sw / 2, 0), 12: (sw / 2, 0), 0: (turn * sw, -0.8 * sw),
             15: (-sw / 2 + wrist[0] * sw, 0.9 * sw + wrist[1] * sw), 16: (sw / 2, 0.9 * sw)}
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    for i, (x, y) in local.items():
        pts[i] = (cx + c * x - s * y, cy + s * x + c * y, 1.0)
    return pts


def _window(frames, seconds=60):
    w = ModuleWindow("modulo-a", "vision:cam0", START)
    for i in range(seconds * FPS):
        w.add(1 / FPS, frames(i / FPS))
    return w


def _flush(w, labels=None, scores=None, seconds=60):
    return w.flush(labels or {}, scores or {}, START + timedelta(seconds=seconds))


@pytest.mark.parametrize("deg", [0, 90, 180])
def test_motion_is_body_relative_so_rotation_does_not_change_it(deg):
    # Drifts 1 shoulder width per second along x for 20 s, hand waving 0.2 sw back and forth.
    w = _window(lambda t: {1: pose(200 + 100 * (t % 20), 300, wrist=(0.2 * (int(t * FPS) % 2), 0), deg=deg)})
    _, sessions = _flush(w, {1: "ast-01"}, {"ast-01": 0.8})
    m = sessions[0].motion
    assert m.speed == pytest.approx(1.0, abs=0.01) and m.stationary_ratio == 0.0  # wrap-around jumps skipped
    assert m.fidget_index == pytest.approx(1.0, abs=0.01)  # one wrist at 2 sw/s, the other still: mean of both
    assert m.torso_angle_dev == 0.0
    assert sessions[0].session_type == "ambiente" and sessions[0].neutral_ok is False
    assert sessions[0].identity.match_score == 0.8


def test_still_person_and_posture_change():
    still = _flush(_window(lambda t: {1: pose(300, 300)}))[1][0].motion
    assert (still.speed, still.stationary_ratio, still.fidget_index, still.torso_angle_dev) == (0.0, 1.0, 0.0, 0.0)
    leaning = _flush(_window(lambda t: {1: pose(300, 300, turn=0.5 if t >= 30 else 0.0)}))[1][0].motion
    assert leaning.torso_angle_dev > 10


def test_pairs_distance_and_facing_each_other():
    face_to_face = lambda t: {1: pose(200, 300, turn=0.3), 2: pose(500, 300, turn=-0.3)}  # noqa: E731
    co, _ = _flush(_window(face_to_face), {1: "ast-01", 2: "ast-02"})
    p = co.pairs[0]
    assert (p.a, p.b, p.seconds_together, p.mean_distance_shoulders, p.facing_ratio) == ("ast-01", "ast-02", 60.0, 3.0, 1.0)
    away = lambda t: {1: pose(200, 300, turn=-0.3), 2: pose(500, 300, turn=0.3)}  # noqa: E731
    assert _flush(_window(away), {1: "ast-01", 2: "ast-02"})[0].pairs[0].facing_ratio == 0.0
    assert facing(body(pose(0, 0, turn=0.3, deg=180)), body(pose(-300, 0, deg=180)))  # upside down too


def test_window_follows_the_contract_rules():
    # ast-01 all window (two tracks: lost and found), ast-02 for 20 s, a 0.5 s blip, an unknown for 30 s.
    def frames(t):
        out = {1 if t < 30 else 4: pose(200, 300)}
        if 10 <= t < 30:
            out[2] = pose(500, 300)
        if 40 <= t < 40.5:
            out[3] = pose(800, 300)
        if t >= 30:
            out[5] = pose(800, 300)
        return out
    co, sessions = _flush(_window(frames), {1: "ast-01", 4: "ast-01", 2: "ast-02", 3: "ast-02"})
    occ = {o.astronaut_id: o.seconds_present for o in co.occupants}
    assert occ == {"ast-01": 60.0, "ast-02": 20.5, "unknown-5": 30.0}  # ast-02's blip merged, no repeats
    pairs = {(p.a, p.b): p.seconds_together for p in co.pairs}
    assert pairs == {("ast-01", "ast-02"): 20.5, ("ast-01", "unknown-5"): 30.0, ("ast-02", "unknown-5"): 0.5}
    assert {s.astronaut_id for s in sessions} == {"ast-01", "ast-02", "unknown-5"}
    assert co.quality == "good"


def test_empty_or_short_windows_send_nothing():
    assert _flush(_window(lambda t: {}, seconds=5), seconds=5) == (None, [])
    co, sessions = _flush(_window(lambda t: {1: pose(300, 300)}, seconds=5), seconds=5)
    assert co.occupants[0].seconds_present == 5.0 and sessions == []  # under 10 s of pose: no motion
    no_pose = _flush(_window(lambda t: {1: None}))
    assert no_pose[0].occupants and no_pose[1] == []
