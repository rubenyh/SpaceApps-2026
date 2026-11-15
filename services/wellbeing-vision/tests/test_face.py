import math

import numpy as np

from wellbeing_vision.anchor import load_anchor, save_neutral
from wellbeing_vision.face import (
    FaceFrame, SessionMetrics, calibration_break, eye_aspect_ratio, neutral_of, neutral_problem, pitch_degrees,
)

NEUTRAL = FaceFrame(0.0, ear=0.30, jaw_open=0.05, brow_down=0.10, lip_press=0.10, pitch=0.0, eye_blink=0.1)


def _frame(t, **kw):
    base = dict(ear=0.30, jaw_open=0.05, brow_down=0.10, lip_press=0.10, pitch=0.0, eye_blink=0.1)
    return FaceFrame(t, **(base | kw))


def _run(fn, seconds=20.0, fps=30):
    m = SessionMetrics(NEUTRAL)
    for i in range(int(seconds * fps)):
        t = i / fps
        m.add(fn(t), t)
    return m


def test_ear_open_vs_closed():
    open_eye = np.array([[0, 0], [3, -2], [7, -2], [10, 0], [7, 2], [3, 2]], float)
    closed = open_eye * [1, 0.1]
    assert eye_aspect_ratio(open_eye) == 0.4
    assert eye_aspect_ratio(closed) < 0.05


def test_pitch_positive_when_rotated_about_x():
    a = math.radians(20)
    rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    assert round(pitch_degrees(rx)) == 20


def test_neutral_median_ignores_one_blink():
    frames = [_frame(i) for i in range(9)] + [_frame(9, ear=0.05, eye_blink=0.7)]
    assert neutral_of(frames).ear == 0.3 and neutral_of(frames).eye_blink == 0.1


def test_steady_face_has_no_events():
    m = _run(lambda t: _frame(t))
    f, ten = m.fatigue(), m.tension()
    assert (f.yawn_count, f.nod_count, f.perclos, f.blink_rate_per_min) == (0, 0, 0.0, 0.0)
    assert f.eye_openness_vs_neutral == 1.0
    assert ten.brow_lower_delta == 0.0


def test_blinks_counted_once_per_closure():
    # 0.1 s closed every 2 s -> 30 blinks/min
    m = _run(lambda t: _frame(t, eye_blink=0.7 if (t % 2) < 0.1 else 0.1))
    assert 29 <= m.fatigue().blink_rate_per_min <= 31


def test_blink_jitter_at_threshold_is_one_blink():
    # Closes above 0.4, reopens below 0.3. Jitter 0.42/0.35 is one closure.
    m = _run(lambda t: _frame(t, eye_blink=(0.42 if int(t * 30) % 2 else 0.35) if 5 <= t < 5.5 else 0.1))
    assert m.blinks.count == 1


def test_far_face_inflating_ear_does_not_hide_closures():
    # Traced: open-eye EAR doubles when the face moves away; eyeBlink still reads the closure.
    m = _run(lambda t: _frame(t, ear=0.6, eye_blink=0.7 if (t % 2) < 0.1 else 0.05))
    assert 29 <= m.fatigue().blink_rate_per_min <= 31


def test_high_open_eye_baseline_raises_the_closure_bar():
    m = SessionMetrics(FaceFrame(0.0, 0.3, 0.05, 0.1, 0.1, 0.0, eye_blink=0.25))
    for i in range(600):
        m.add(_frame(i / 30, eye_blink=0.45), i / 30)  # over 0.4 but under 0.25 + 0.25
    assert m.fatigue().perclos == 0.0


def test_calibration_breaks_on_blink_head_move_and_talking():
    steady = [_frame(i / 30) for i in range(30)]
    assert calibration_break(steady, _frame(1.0)) is None
    assert calibration_break(steady, _frame(1.0, eye_blink=0.6)) == "blink"
    assert calibration_break(steady, _frame(1.0, yaw=8.0)) == "move"
    assert calibration_break(steady, _frame(1.0, jaw_open=0.3)) == "mouth"


def test_neutral_plausibility_and_anchor(tmp_path):
    assert neutral_problem(_frame(0, eye_blink=0.35), None) == "squint"  # S3-like: calibrated half-closed
    path = tmp_path / "ast-01.jsonl"
    for ear in (0.30, 0.31, 0.29):
        save_neutral(path, _frame(0, ear=ear))
    path.write_text(path.read_text() + '{"torn', encoding="utf-8")
    anchor, n = load_anchor(path)
    assert n == 3 and anchor.ear == 0.30
    assert neutral_problem(_frame(0, ear=0.31), anchor) is None
    assert neutral_problem(_frame(0, ear=0.22), anchor) == "anchor"


def test_relaxing_below_neutral_is_not_negative_tension():
    m = _run(lambda t: _frame(t, brow_down=0.0, lip_press=0.0))
    assert m.tension().brow_lower_delta == 0.0 and m.tension().lip_press_delta == 0.0


def test_yawn_needs_sustained_jaw_and_talking_does_not_count():
    talking = _run(lambda t: _frame(t, jaw_open=0.7 if (t % 1) < 0.4 else 0.05))
    assert talking.fatigue().yawn_count == 0
    yawn = _run(lambda t: _frame(t, jaw_open=0.8 if 5 <= t < 8 else 0.05))
    assert yawn.fatigue().yawn_count == 1


def test_nod_and_tension_vs_neutral():
    m = _run(lambda t: _frame(t, pitch=25.0 if 3 <= t < 4 else 0.0, brow_down=0.40))
    assert m.fatigue().nod_count == 1
    assert m.tension().brow_lower_delta == 0.3


def test_no_face_means_none_not_zero():
    m = _run(lambda t: None, seconds=2)
    assert m.fatigue().perclos is None and m.tension().lip_press_delta is None
    assert m.valid_frame_ratio == 0.0


def test_short_session_rates_are_not_measurable():
    m = _run(lambda t: _frame(t), seconds=5)
    assert m.fatigue().blink_rate_per_min is None and m.fatigue().yawn_count == 0


def test_sustained_peak_catches_brief_grimace_the_mean_dilutes():
    # 1.5 s frown at +0.4 in a 20 s log: mean ~0.03, sustained peak 0.4.
    m = _run(lambda t: _frame(t, brow_down=0.5 if 8 <= t < 9.5 else 0.10))
    assert m.tension().brow_lower_delta < 0.05
    assert m.tension().brow_lower_peak_1s == 0.4


def test_peak_needs_a_continuous_hold():
    # 0.6 s spikes never last 1 s; a face dropout also breaks the hold.
    spikes = _run(lambda t: _frame(t, lip_press=0.6 if (t % 2) < 0.6 else 0.10))
    assert spikes.tension().lip_press_peak_1s == 0.0
    gap = _run(lambda t: None if 5.5 <= t < 5.6 else _frame(t, lip_press=0.6 if 5 <= t < 6 else 0.10))
    assert gap.tension().lip_press_peak_1s == 0.0


def test_yawn_at_new_threshold_and_face_width():
    m = _run(lambda t: _frame(t, jaw_open=0.45 if 5 <= t < 6.2 else 0.05))
    assert m.fatigue().yawn_count == 1
    xy = np.zeros((478, 2))
    xy[234], xy[454] = (100, 200), (300, 200)
    from wellbeing_vision.face import face_frame
    from types import SimpleNamespace as NS
    names = ["jawOpen", "browDownLeft", "browDownRight", "mouthPressLeft", "mouthPressRight",
             "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookUpLeft", "eyeLookUpRight"]
    ff = face_frame(0.0, xy, [NS(category_name=n, score=0.1) for n in names], np.eye(4))
    assert ff.face_px == 200.0 and ff.eye_blink == 0.1


def _talking(t):
    # 4 syllables/s: jaw opens and closes, and the lips press on the closed phase (m/b/p).
    closed = (t * 4) % 1 < 0.5
    return {"jaw_open": 0.05 if closed else 0.30, "lip_press": 0.6 if closed else 0.10}


def test_talking_is_not_lip_press_but_a_silent_press_is():
    m = _run(lambda t: _frame(t, **_talking(t)) if t < 8 else _frame(t, lip_press=0.4 if 12 <= t < 14 else 0.10))
    assert m.tension().lip_press_peak_1s == 0.3
    # Mean over 12 quiet s: the 2 s press alone gives 0.05; the first syllable, before the second opening
    # proves it is talking, leaks.
    assert 0.05 <= m.tension().lip_press_delta < 0.08


def test_mostly_talking_reports_lip_press_as_null():
    m = _run(lambda t: _frame(t, **_talking(t)) if t < 15 else _frame(t))
    assert m.tension().lip_press_delta is None and m.tension().lip_press_peak_1s is None
    assert m.tension().brow_lower_delta == 0.0


def test_reading_posture_is_not_closure_tension_or_nods():
    # S3-like: 5 s looking down with lowered lids (eyeBlink 0.5) and lowered brows, three times.
    def reading(t):
        down = (t % 10) >= 5
        return _frame(t, look_down=0.5 if down else 0.0, pitch=18.0 if down else 0.0,
                      eye_blink=0.5 if down else 0.1, brow_down=0.6 if down else 0.1)
    m = _run(reading, seconds=30)
    f, ten = m.fatigue(), m.tension()
    assert f.nod_count == 0
    assert f.perclos == 0.0  # the 0.5 s before it counts as looking down is dropped too
    assert ten.brow_lower_peak_1s == 0.0
    assert m.valid_frame_ratio < 0.6  # looking away from the camera lowers quality


def test_deep_closure_counts_even_looking_down():
    # Drowsy: eyes shut and head down for 3 s.
    m = _run(lambda t: _frame(t, look_down=0.5, eye_blink=0.7) if 5 <= t < 8 else _frame(t))
    assert m.fatigue().perclos == 0.15


def test_blink_while_glancing_down_still_counts():
    # A short glance down (0.3 s, under the hold) with a closure: kept.
    m = _run(lambda t: _frame(t, look_down=0.5, eye_blink=0.5) if (t % 2) < 0.3 else _frame(t))
    assert m.fatigue().perclos > 0.1 and m.blinks.count == 10


def test_nod_is_a_drop_and_return_not_a_posture_or_jitter():
    nods = _run(lambda t: _frame(t, pitch=25.0 if (t % 5) < 1 else 0.0, look_up=0.3))  # eyes stay on camera
    assert nods.fatigue().nod_count == 4
    jitter = _run(lambda t: _frame(t, pitch=(16.0 if int(t * 30) % 2 else 14.0) if 5 <= t < 12 else 0.0))
    assert jitter.fatigue().nod_count == 0


def test_single_mouth_openings_are_not_talking():
    # One short opening every 2 s (swallowing, a sigh): never two within 1 s.
    m = _run(lambda t: _frame(t, jaw_open=0.15 if (t % 2) < 0.15 else 0.05))
    assert m.quiet_s > 19


def test_talking_with_a_still_jaw_is_caught_by_lip_swings_but_a_held_press_is_not():
    # Traced: talking to the camera barely moves jawOpen, but mouthPress swings below neutral (~ -0.15).
    talk = _run(lambda t: _frame(t, lip_press=0.10 + (-0.25 if int(t * 6) % 2 else -0.05)))
    assert talk.quiet_s < 2
    # A held press: rises to +0.4 over neutral with small jitter, 3 s, twice.
    press = _run(lambda t: _frame(t, lip_press=0.5 + 0.03 * (int(t * 10) % 2) if (t % 10) < 3 else 0.10))
    assert press.talking_s < 1 and press.tension().lip_press_peak_1s >= 0.4
