"""The ambient loop with fake cameras, faces and clock: no models, no window."""

import itertools

import numpy as np

import wellbeing_vision.ambiente as amb
from wellbeing_vision.config import Settings
from wellbeing_vision.identity import Face, Gallery

V = np.ones(128, np.float32) / np.sqrt(128)


def _run(monkeypatch, tmp_path, sees, **kw):
    """Run the loop with fake cameras; sees(camera, n) says if that camera sees ast-01 at read n."""
    reads = itertools.count()

    class Cam:
        def __init__(self, i):
            self.i = i

        def read(self):
            frame = np.zeros((480, 640, 3), np.uint8)
            frame[0, 0, 0] = sees(self.i, next(reads))
            return True, frame

        def release(self):
            pass

    class FakeID:
        deg = 0

        def detect(self, frame, orientations):
            row = np.zeros(15, np.float32)
            row[14] = 0.95
            return [Face(np.array([300.0, 100, 400, 200]), row, 0)] if frame[0, 0, 0] else []

        def template(self, frame, face):
            return V

    ticks = itertools.count()
    monkeypatch.setattr(amb.time, "monotonic", lambda: next(ticks) * 0.05)
    monkeypatch.setattr(amb, "open_configured", lambda i, *a: Cam(i))
    monkeypatch.setattr(amb, "face_id", lambda s: FakeID())
    g = Gallery(tmp_path)
    g.people = {"ast-01": {"enrolled": V[None], "auto": np.empty((0, 128), np.float32)}}
    monkeypatch.setattr(amb, "gallery_of", lambda s: g)
    monkeypatch.setattr(amb, "_pose_landmarker", lambda s: type("P", (), {"close": lambda self: None})())
    monkeypatch.setattr(amb, "detect_poses", lambda pose, frame, deg, ms: [])
    monkeypatch.setattr(amb, "render", lambda frame, *a, **k: frame)
    monkeypatch.setattr(amb._Window, "__init__", lambda self, name: None)
    monkeypatch.setattr(amb._Window, "show", lambda self, canvas: True)
    sent = []
    sink = type("S", (), {"send": lambda self, route, payload: sent.append((route, payload))})()
    amb.run_ambiente(Settings(data_dir=tmp_path), sink, [0, 1], window_s=10, seconds=40, **kw)
    return [p for r, p in sent if r == "/wellbeing/co-presence"]


def test_two_modules_send_windows_and_see_a_transfer(monkeypatch, tmp_path, capsys):
    co = _run(monkeypatch, tmp_path, lambda cam, n: cam == (n // 2 >= 150))  # cam 0, then cam 1
    assert {c.module_id for c in co} == {"modulo-a", "modulo-b"}
    assert all(o.astronaut_id == "ast-01" and 0 < o.seconds_present <= 10 for c in co for o in c.occupants)
    assert capsys.readouterr().out.count("Transfer ast-01: modulo-a -> modulo-b") == 1


def test_overlapping_cameras_count_one_module_once(monkeypatch, tmp_path, capsys):
    co = _run(monkeypatch, tmp_path, lambda cam, n: True, overlap=True)  # both cameras see ast-01 always
    assert {(c.module_id, c.source) for c in co} == {("modulo-a", "vision:cam0+cam1")}
    assert all([o.astronaut_id for o in c.occupants] == ["ast-01"] for c in co)
    assert "Transfer" not in capsys.readouterr().out


def test_transfer_needs_the_old_module_left_and_the_new_one_held():
    homes = amb.Homes()
    for k in range(40):  # both cameras see ast-01 for 4 s: stays in modulo-a, no transfer
        assert homes.update({"ast-01": {"modulo-a", "modulo-b"}}, k * 0.1) == []
    assert homes.counted_in("ast-01", {"modulo-a", "modulo-b"}) == "modulo-a"
    events = [e for k in range(40, 120) for e in homes.update({"ast-01": {"modulo-b"}}, k * 0.1)]
    assert events == ["ast-01: modulo-a -> modulo-b"]  # once, 3 s after leaving modulo-a


def test_same_astronaut_in_two_cameras_is_counted_once():
    from wellbeing_vision.tracker import Track

    def cam(module, *tracks):
        return type("C", (), {"module_id": module, "seen": list(tracks)})()

    a, b = Track(1, None, 0.0), Track(2, None, 0.0)
    a.astronaut = b.astronaut = "ast-01"
    homes = amb.Homes()
    sightings = {"ast-01": {"modulo-a", "modulo-b"}}
    homes.update(sightings, 0.0)
    amb.assign([cam("modulo-a", a), cam("modulo-b", b)], homes, sightings)
    assert a.elsewhere is None and b.elsewhere == "modulo-a"  # shown as "ast-01 (seen from modulo-a)"


def test_panel_groups_unknowns_and_never_overflows():
    from wellbeing_vision.motion import ModuleWindow
    from wellbeing_vision.overlay import render

    w = ModuleWindow("modulo-a", "vision:cam0", None)
    w.add(1.0, {i: None for i in range(1, 30)})
    rows = amb.panel_rows(Settings(), w, {1: "ast-01"}, [])
    assert [r.label for r in rows][:2] == ["ast-01", "Unknown: 28 people"]
    many = [("SECTION", [amb.Row(f"row {i}", "x") for i in range(40)])]
    render(np.zeros((480, 640, 3), np.uint8), "T", "S", many, "footer")  # no exception, rows cut


def test_per_camera_flip_and_turn():
    from wellbeing_vision.capture import orientation

    frame = np.zeros((2, 3, 3), np.uint8)
    frame[0, 0] = 255  # top-left
    flip, desc = orientation(True, 0)
    assert flip(frame)[0, 2, 0] == 255 and desc == "mirrored"
    both, desc = orientation(True, 90)
    assert both(frame).shape == (3, 2, 3) and desc == "mirrored, turned 90°"
    assert orientation(False, 0) == (None, "as delivered")
