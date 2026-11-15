"""The ambient loop with fake cameras, faces and clock: no models, no window."""

import itertools

import numpy as np

import wellbeing_vision.ambiente as amb
from wellbeing_vision.config import Settings
from wellbeing_vision.identity import Face, Gallery

V = np.ones(128, np.float32) / np.sqrt(128)


def test_two_modules_send_windows_and_see_a_transfer(monkeypatch, tmp_path, capsys):
    reads = itertools.count()

    class Cam:
        def __init__(self, i):
            self.i = i

        def read(self):
            n = next(reads)
            frame = np.zeros((720, 1280, 3), np.uint8)
            frame[0, 0] = (self.i, n // 2 >= 150, 0)  # tells FakeID which camera and which half of the run
            return True, frame

        def release(self):
            pass

    class FakeID:
        deg = 0

        def detect(self, frame, orientations):
            cam, moved = frame[0, 0, 0], frame[0, 0, 1]
            return [Face(np.array([500.0, 200, 700, 400]), np.zeros(15, np.float32), 0)] if cam == moved else []

        def template(self, frame, face):
            return V

    ticks = itertools.count()
    monkeypatch.setattr(amb.time, "monotonic", lambda: next(ticks) * 0.05)
    monkeypatch.setattr(amb, "open_camera", lambda i, backend: Cam(i))
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
    amb.run_ambiente(Settings(data_dir=tmp_path), sink, [0, 1], window_s=10, seconds=40)

    co = [p for r, p in sent if r == "/wellbeing/co-presence"]
    assert {c.module_id for c in co} == {"modulo-a", "modulo-b"}
    assert all(o.astronaut_id == "ast-01" and 0 < o.seconds_present <= 10 for c in co for o in c.occupants)
    assert "Transfer ast-01: modulo-a -> modulo-b" in capsys.readouterr().out
