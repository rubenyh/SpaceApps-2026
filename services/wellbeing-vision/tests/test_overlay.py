import numpy as np

from wellbeing_vision.overlay import AMBER, GREEN, RED, Notice, Row, render, severity

# Accented labels on purpose: the TTF font must keep rendering them.
SECTIONS = [("FATIGA", [Row("Apertura de ojos", "88 %", GREEN, 0.7, 0.5), Row("Parpadeos", "18 /min")]),
            ("TENSIÓN", [Row("Cejo fruncido", "12 %", AMBER, 0.3, 0.5)])]


def _frame():
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)


def test_render_never_touches_input_and_does_not_accumulate():
    frame = _frame()
    before = frame.copy()
    a = render(frame, "BITÁCORA · ast-01", "GRABANDO", SECTIONS, "Umbrales provisionales",
               Notice("Keep your face relaxed", "Calibrating", progress=0.5), [(0.5, 0.5)])
    b = render(frame, "BITÁCORA · ast-01", "GRABANDO", SECTIONS, "Umbrales provisionales",
               Notice("Keep your face relaxed", "Calibrating", progress=0.5), [(0.5, 0.5)])
    assert np.array_equal(frame, before)
    assert np.array_equal(a, b)
    assert a.shape == (720, 960 + 480, 3)


def test_changing_a_value_only_changes_that_frame():
    frame = _frame()
    one = render(frame, "T", "S", [("F", [Row("Bostezos", "1")])], "f")
    two = render(frame, "T", "S", [("F", [Row("Bostezos", "2")])], "f")
    again = render(frame, "T", "S", [("F", [Row("Bostezos", "1")])], "f")
    assert not np.array_equal(one, two) and np.array_equal(one, again)


def test_severity_colors():
    assert severity(0.05, 0.15) == GREEN
    assert severity(0.12, 0.15) == AMBER
    assert severity(0.20, 0.15) == RED
    # Eye openness: lower is worse.
    assert severity(1.0, 0.6, higher_is_worse=False) == GREEN
    assert severity(0.7, 0.6, higher_is_worse=False) == AMBER
    assert severity(0.5, 0.6, higher_is_worse=False) == RED


def test_live_rows_show_dash_without_data_and_red_over_threshold():
    from wellbeing_vision.bitacora import live_sections
    from wellbeing_vision.face import FaceFrame, SessionMetrics

    m = SessionMetrics(FaceFrame(0, 0.3, 0.05, 0.1, 0.1, 0.0))
    empty = {r.label: r for _, rows in live_sections(m, {}) for r in rows}
    assert empty["PERCLOS (eyes closed)"].value == "—" and empty["Blinks"].value == "—"
    hot = {r.label: r for _, rows in live_sections(m, {"perclos": 0.25, "eyes": 0.5, "brow": 0.05}) for r in rows}
    assert hot["PERCLOS (eyes closed)"].color == RED and hot["Eye openness"].color == RED
    assert hot["Brow lowering"].color == GREEN
    talking = {r.label: r for _, rows in live_sections(m, {"speaking": True}) for r in rows}
    assert talking["Lip press"].value == "talking"


def test_trace_never_overwrites(tmp_path):
    from wellbeing_vision.bitacora import _unused

    first = tmp_path / "t.csv"
    assert _unused(first) == first
    first.write_text("x")
    assert _unused(first) == tmp_path / "t-2.csv"
    (tmp_path / "t-2.csv").write_text("x")
    assert _unused(first) == tmp_path / "t-3.csv"
