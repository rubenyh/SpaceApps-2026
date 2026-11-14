import math

import numpy as np

from wellbeing_vision.face import FaceFrame, SessionMetrics, eye_aspect_ratio, neutral_of, pitch_degrees

NEUTRAL = FaceFrame(0.0, ear=0.30, jaw_open=0.05, brow_down=0.10, lip_press=0.10, pitch=0.0)


def _frame(t, **kw):
    base = dict(ear=0.30, jaw_open=0.05, brow_down=0.10, lip_press=0.10, pitch=0.0)
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
    frames = [_frame(i, ear=0.3) for i in range(9)] + [_frame(9, ear=0.05)]
    assert neutral_of(frames).ear == 0.3


def test_steady_face_has_no_events():
    m = _run(lambda t: _frame(t))
    f, ten = m.fatigue(), m.tension()
    assert (f.yawn_count, f.nod_count, f.perclos, f.blink_rate_per_min) == (0, 0, 0.0, 0.0)
    assert f.eye_openness_vs_neutral == 1.0
    assert ten.brow_lower_delta == 0.0


def test_blinks_counted_once_per_closure():
    # 0.1 s closed every 2 s -> 30 blinks/min
    m = _run(lambda t: _frame(t, ear=0.05 if (t % 2) < 0.1 else 0.30))
    assert 29 <= m.fatigue().blink_rate_per_min <= 31


def test_ear_jitter_at_threshold_is_one_blink():
    # Neutral 0.30 -> closes below 0.18, reopens above 0.21. Jitter 0.17/0.19 is one closure.
    m = _run(lambda t: _frame(t, ear=(0.17 if int(t * 30) % 2 else 0.19) if 5 <= t < 5.5 else 0.30))
    assert m.blinks.count == 1


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
    assert m.tension_peaks()["brow_lower_peak_1s"] == 0.4


def test_peak_needs_a_continuous_hold():
    # 0.6 s spikes never last 1 s; a face dropout also breaks the hold.
    spikes = _run(lambda t: _frame(t, lip_press=0.6 if (t % 2) < 0.6 else 0.10))
    assert spikes.tension_peaks()["lip_press_peak_1s"] == 0.0
    gap = _run(lambda t: None if 5.5 <= t < 5.6 else _frame(t, lip_press=0.6 if 5 <= t < 6 else 0.10))
    assert gap.tension_peaks()["lip_press_peak_1s"] == 0.0


def test_yawn_at_new_threshold_and_face_width():
    m = _run(lambda t: _frame(t, jaw_open=0.45 if 5 <= t < 6.2 else 0.05))
    assert m.fatigue().yawn_count == 1
    xy = np.zeros((478, 2))
    xy[234], xy[454] = (100, 200), (300, 200)
    from wellbeing_vision.face import face_frame
    from types import SimpleNamespace as NS
    names = ["jawOpen", "browDownLeft", "browDownRight", "mouthPressLeft", "mouthPressRight",
             "eyeBlinkLeft", "eyeBlinkRight"]
    ff = face_frame(0.0, xy, [NS(category_name=n, score=0.1) for n in names], np.eye(4))
    assert ff.face_px == 200.0 and ff.eye_blink == 0.1
