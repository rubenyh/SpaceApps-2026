import queue
import threading

import cv2

READ_TIMEOUT_S = 2.0


class Camera:
    """A VideoCapture read in a background thread. read() waits at most timeout_s and then reports failure,
    so a camera that stops delivering ends the session instead of freezing it (a log once sat 41 min inside
    cap.read()). Only the newest frame is kept."""

    def __init__(self, cap, timeout_s: float = READ_TIMEOUT_S) -> None:
        self.cap, self.timeout_s, self.running = cap, timeout_s, True
        self.frames: queue.Queue = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while self.running:
            ok, frame = self.cap.read()
            try:
                self.frames.get_nowait()  # drop the frame nobody took yet
            except queue.Empty:
                pass
            self.frames.put(frame if ok else None)
            if not ok:
                return

    def read(self):
        """(ok, frame) like VideoCapture.read(); (False, None) after timeout_s without a frame."""
        try:
            frame = self.frames.get(timeout=self.timeout_s)
        except queue.Empty:
            return False, None
        return frame is not None, frame

    def release(self) -> None:
        self.running = False
        self.thread.join(timeout=self.timeout_s)
        if not self.thread.is_alive():  # a read stuck in the driver: leave it to process exit
            self.cap.release()


def open_camera(index: int, width: int = 1280, height: int = 720) -> Camera:
    """Open a camera asking for width x height and print what it actually delivers."""
    # CAP_DSHOW opens much faster than the default backend on Windows.
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Camera {index} not available (in use by another process or not connected).")
    # Many webcams only reach 720p at 30 fps in MJPG; the default YUY2 drops to 5-10 fps.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    got = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    print(f"Camera {index}: {got[0]}x{got[1]} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps (asked {width}x{height})")
    return Camera(cap)
