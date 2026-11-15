"""Backend fallback with fake captures: no camera needed."""

import numpy as np
import pytest

import wellbeing_vision.capture as cap_mod
from wellbeing_vision.capture import CAP_DSHOW, CAP_MSMF, open_camera


class FakeCap:
    """behaviour per backend: 'raise', 'closed', 'silent' (opens, never a frame) or a (w, h) size."""

    behaviour: dict = {}

    def __init__(self, index, api):
        b = self.behaviour[api]
        if b == "raise":
            raise cap_mod.cv2.error("VIDEOIO(DSHOW): raised unknown C++ exception")
        self.b = b

    def isOpened(self):
        return self.b != "closed"

    def set(self, *a):
        return True

    def get(self, prop):
        return 30.0

    def read(self):
        if self.b == "silent":
            return False, None
        w, h = self.b
        return True, np.zeros((h, w, 3), np.uint8)

    def release(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(cap_mod.cv2, "VideoCapture", FakeCap)
    return FakeCap.behaviour


def test_auto_falls_back_to_msmf_when_dshow_throws(fake, capsys):
    fake.update({CAP_DSHOW: "raise", CAP_MSMF: (640, 480)})
    cam = open_camera(1, "auto", first_frame_s=0.2)
    out = capsys.readouterr().out
    assert cam.read()[0] and "Camera 1: MSMF 640x480" in out and "Warning: camera 1 gives 640x480" in out
    cam.release()


def test_auto_falls_back_when_dshow_opens_but_gives_no_frame(fake, capsys):
    fake.update({CAP_DSHOW: "silent", CAP_MSMF: (1280, 720)})
    cam = open_camera(0, "auto", first_frame_s=0.2)
    out = capsys.readouterr().out
    assert "Camera 0: MSMF 1280x720" in out and "Warning" not in out
    cam.release()


def test_auto_keeps_dshow_when_it_works(fake, capsys):
    fake.update({CAP_DSHOW: (1280, 720), CAP_MSMF: "raise"})
    open_camera(0, "auto", first_frame_s=0.2).release()
    assert "Camera 0: DSHOW 1280x720" in capsys.readouterr().out


def test_explicit_backend_is_the_only_one_tried(fake):
    fake.update({CAP_DSHOW: (1280, 720), CAP_MSMF: "closed"})
    with pytest.raises(SystemExit) as e:
        open_camera(0, "msmf", first_frame_s=0.2)
    assert "Camera 0 not available. Tried msmf: did not open" in str(e.value)


def test_no_backend_works_is_a_loud_error(fake):
    fake.update({CAP_DSHOW: "raise", CAP_MSMF: "silent"})
    with pytest.raises(SystemExit) as e:
        open_camera(3, "auto", first_frame_s=0.2)
    msg = str(e.value)
    assert e.value.code != 0 and "Camera 3 not available" in msg
    assert "dshow: VIDEOIO(DSHOW): raised unknown C++ exception" in msg and "msmf: opened but no frame" in msg
