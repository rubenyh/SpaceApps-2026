"""The log loop with a fake camera and clock: no models, no window."""

import itertools
import threading
import time

import numpy as np

import wellbeing_vision.bitacora as b
from wellbeing_vision.capture import Camera
from wellbeing_vision.config import Settings
from wellbeing_vision.face import FaceFrame
from wellbeing_vision.identity import Gallery
from wellbeing_vision.sink import Sink


class _FakeCap:
    def read(self):
        return True, np.zeros((720, 1280, 3), np.uint8)

    def release(self):
        pass


def _run(monkeypatch, tmp_path, clock, faces=None, claimed="ast-01"):
    monkeypatch.setattr(b.time, "monotonic", clock)
    monkeypatch.setattr(b, "open_configured", lambda i, *a: _FakeCap())
    monkeypatch.setattr(b, "_landmarker", lambda s: type("L", (), {"close": lambda self: None})())
    monkeypatch.setattr(b, "FaceCrop", lambda p: None)
    monkeypatch.setattr(b, "model_path", lambda d, n: n)
    monkeypatch.setattr(b, "face_id", lambda s: faces)
    monkeypatch.setattr(b, "gallery_of", lambda s: _gallery(tmp_path) if faces else Gallery(tmp_path))
    monkeypatch.setattr(b, "render", lambda frame, *a, **k: frame)
    for name in ("namedWindow", "imshow", "destroyAllWindows", "setWindowProperty"):
        monkeypatch.setattr(b.cv2, name, lambda *a, **k: None)
    monkeypatch.setattr(b.cv2, "waitKey", lambda *a: -1)
    monkeypatch.setattr(b.cv2, "getWindowProperty", lambda *a: 1)
    monkeypatch.setattr(b, "_detect", lambda lm, cr, frame, t, ms: (
        FaceFrame(t, 0.3, 0.05, 0.1, 0.1, 0.0, face_px=250, eye_blink=0.1), np.zeros((478, 2))))
    sent = []
    sink = Sink("http://x", tmp_path / "o.jsonl", dry_run=True)
    monkeypatch.setattr(sink, "send", lambda route, payload: sent.append(payload))
    return b.run_bitacora(Settings(data_dir=tmp_path), sink, claimed, 0, 60), sent


def _gallery(tmp_path):
    g = Gallery(tmp_path)
    v = np.ones(128, np.float32) / np.sqrt(128)
    g.people = {"ast-01": {"enrolled": v[None], "auto": np.empty((0, 128), np.float32)},
                "ast-02": {"enrolled": -v[None], "auto": np.empty((0, 128), np.float32)}}
    return g


def test_stalled_camera_ends_the_log_at_the_last_frame(monkeypatch, tmp_path):
    # 20 s of frames at 30 fps, then the next frame arrives 41 min later (the R3 log).
    ticks = itertools.count()

    def clock():
        i = next(ticks)
        return i / 30 if i < 700 else 700 / 30 + 2460 + (i - 700) / 30

    session, sent = _run(monkeypatch, tmp_path, clock)
    duration = (session.ended_at - session.started_at).total_seconds()
    assert 15 < duration < 21 and sent == [session]


def test_ended_at_is_the_last_frame_and_respects_seconds(monkeypatch, tmp_path):
    ticks = itertools.count()
    session, _ = _run(monkeypatch, tmp_path, lambda: next(ticks) / 30)
    assert abs((session.ended_at - session.started_at).total_seconds() - 60) < 0.1


def test_someone_elses_face_is_not_sent(monkeypatch, tmp_path):
    v = np.ones(128, np.float32) / np.sqrt(128)
    face = type("F", (), {"width": 200.0})()
    faces = type("ID", (), {"detect": lambda self, frame: [face], "template": lambda self, frame, f: -v})()
    ticks = itertools.count()
    session, sent = _run(monkeypatch, tmp_path, lambda: next(ticks) / 30, faces=faces)  # face is ast-02
    assert session is None and sent == []
    assert not (tmp_path / "neutrals" / "ast-01.jsonl").exists()


def test_camera_read_times_out_instead_of_freezing():
    release = threading.Event()

    class Stuck:
        def read(self):
            release.wait()
            return False, None

        def release(self):
            pass

    cam = Camera(Stuck(), timeout_s=0.2)
    t = time.monotonic()
    assert cam.read() == (False, None) and time.monotonic() - t < 1
    release.set()
    cam.release()
