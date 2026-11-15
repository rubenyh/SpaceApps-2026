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


CAP_DSHOW, CAP_MSMF = cv2.CAP_DSHOW, cv2.CAP_MSMF
BACKENDS = {"dshow": CAP_DSHOW, "msmf": CAP_MSMF}
# DSHOW first: it opens faster on Windows. Some USB phone-webcam apps only work with MSMF (DSHOW throws).
AUTO_ORDER = ("dshow", "msmf")


def _try(index: int, backend: str, width: int, height: int, first_frame_s: float) -> tuple[Camera | None, str]:
    """Open one camera with one backend and wait for a first frame.
    (camera, "WxH it delivers") or (None, why it failed)."""
    try:
        cap = cv2.VideoCapture(index, BACKENDS[backend])
    except cv2.error as e:  # e.g. "VIDEOIO(DSHOW): raised unknown C++ exception"
        return None, f"{backend}: {str(e).strip().splitlines()[-1]}"
    if not cap.isOpened():
        cap.release()
        return None, f"{backend}: did not open"
    # Many webcams only reach 720p at 30 fps in MJPG; the default YUY2 drops to 5-10 fps.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cam = Camera(cap, timeout_s=first_frame_s)
    ok, frame = cam.read()
    if not ok:
        cam.release()
        return None, f"{backend}: opened but no frame in {first_frame_s:.0f} s"
    cam.timeout_s = READ_TIMEOUT_S
    return cam, "{}x{}".format(*frame.shape[1::-1])


def open_camera(index: int, backend: str = "auto", width: int = 1280, height: int = 720,
                first_frame_s: float = READ_TIMEOUT_S) -> Camera:
    """Open a camera asking for width x height. auto tries DSHOW, then MSMF. Prints the backend and the
    resolution it really delivers. Exits with an error (never silently) if no backend gives frames."""
    tried = []
    for name in AUTO_ORDER if backend == "auto" else (backend,):
        cam, info = _try(index, name, width, height, first_frame_s)
        if cam is None:
            tried.append(info)
            continue
        print(f"Camera {index}: {name.upper()} {info} @ {cam.cap.get(cv2.CAP_PROP_FPS):.0f} fps "
              f"(asked {width}x{height})")
        if info != f"{width}x{height}":
            print(f"  Warning: camera {index} gives {info}, not {width}x{height}. Faces look smaller: "
                  "in the daily log sit closer or lower WELLBEING_VISION_MIN_FACE_PX.")
        return cam
    raise SystemExit(f"Camera {index} not available. Tried {', '.join(tried)}. Check the index, close other apps "
                     "using it, or pick a backend with --backend dshow|msmf.")
