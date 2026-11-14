"""Daily video log: 3 s neutral of the day, then fatigue and tension live, then one summary.
Frames stay in memory only; nothing is written to disk except the summary."""

import time
from datetime import UTC, datetime

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

from wellbeing_vision.capture import open_camera
from wellbeing_vision.config import Settings
from wellbeing_vision.download import model_path
from wellbeing_vision.face import LEFT_EYE, RIGHT_EYE, FaceFrame, SessionMetrics, face_frame, neutral_of
from wellbeing_vision.schemas import Identity, VisionSession
from wellbeing_vision.sink import Sink

NEUTRAL_S = 3.0
NEUTRAL_TIMEOUT_S = 30.0
WINDOW = "Bitacora - wellbeing-vision"
GREEN, AMBER, WHITE = (80, 220, 80), (0, 190, 255), (240, 240, 240)
EYE_AND_MOUTH = (*RIGHT_EYE, *LEFT_EYE, 13, 14, 61, 291)


def quality_of(valid_frame_ratio: float) -> str:
    # PROVISIONAL: share of frames with a usable face.
    return "good" if valid_frame_ratio >= 0.8 else "suspect" if valid_frame_ratio >= 0.5 else "bad"


def _landmarker(settings: Settings) -> FaceLandmarker:
    return FaceLandmarker.create_from_options(FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path(settings.models_dir, "face_landmarker.task"))),
        running_mode=RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    ))


def _text(img, lines: list[tuple[str, tuple]], x: int = 12, y: int = 28) -> None:
    for i, (s, color) in enumerate(lines):
        pos = (x, y + i * 26)
        cv2.putText(img, s, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, s, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 1, cv2.LINE_AA)


def _live_lines(m: SessionMetrics, ff: FaceFrame | None, left_s: float) -> list[tuple[str, tuple]]:
    n = m.neutral
    lines = [(f"GRABANDO  {left_s:4.0f} s   (q = terminar)", WHITE)]
    if ff is None:
        return lines + [("Sin cara visible", AMBER)]
    perclos = m.closed_s / m.valid_s if m.valid_s else 0.0
    ratio = ff.ear / n.ear if n.ear else 0.0
    brow, lip = ff.brow_down - n.brow_down, ff.lip_press - n.lip_press
    return lines + [
        ("FATIGA", WHITE),
        (f"  apertura ojos vs neutral  {ratio:4.2f}", AMBER if ratio < 0.8 else GREEN),
        (f"  parpadeos {m.blinks.count:3d}   PERCLOS {perclos:5.1%}", AMBER if perclos > 0.15 else GREEN),
        (f"  bostezos {m.yawns.count}   cabeceos {m.nods.count}   pitch {ff.pitch - n.pitch:+5.1f}", WHITE),
        ("TENSION (vs neutral)", WHITE),
        (f"  cejo fruncido   {brow:+5.2f}", AMBER if brow > 0.2 else GREEN),
        (f"  labios apretados {lip:+5.2f}", AMBER if lip > 0.2 else GREEN),
        ("Umbrales PROVISIONALES", (160, 160, 160)),
    ]


def run_bitacora(settings: Settings, sink: Sink, astronaut_id: str, camera: int, seconds: float) -> VisionSession | None:
    landmarker = _landmarker(settings)
    cap = open_camera(camera)
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    t0, last_ms = time.monotonic(), -1
    neutral_frames: list[FaceFrame] = []
    metrics: SessionMetrics | None = None
    started_at = rec_t0 = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera stopped delivering frames.")
                break
            frame = cv2.flip(frame, 1)  # mirror view; metrics average both eyes so this is harmless
            t = time.monotonic() - t0
            last_ms = max(int(t * 1000), last_ms + 1)
            h, w = frame.shape[:2]
            res = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), last_ms
            )
            ff = None
            if res.face_landmarks:
                lm = res.face_landmarks[0]
                ff = face_frame(t, lm, res.face_blendshapes[0], res.facial_transformation_matrixes[0], w, h)
                for i in EYE_AND_MOUTH:
                    cv2.circle(frame, (int(lm[i].x * w), int(lm[i].y * h)), 2, GREEN, -1)

            if metrics is None:
                # The neutral must be continuous: losing the face restarts it.
                neutral_frames = neutral_frames + [ff] if ff else []
                held = neutral_frames[-1].t - neutral_frames[0].t if neutral_frames else 0.0
                _text(frame, [("CALIBRACION: mira a la camara, cara relajada", WHITE),
                              (f"neutral {held:3.1f} / {NEUTRAL_S:.0f} s", GREEN if ff else AMBER)])
                if held >= NEUTRAL_S:
                    metrics = SessionMetrics(neutral_of(neutral_frames))
                    started_at, rec_t0 = datetime.now(UTC), t
                elif t > NEUTRAL_TIMEOUT_S:
                    print("Calibration failed: no steady face for 3 s. No summary sent.")
                    break
            else:
                metrics.add(ff, t)
                _text(frame, _live_lines(metrics, ff, seconds - (t - rec_t0)))
                if t - rec_t0 >= seconds:
                    break

            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()

    if metrics is None or metrics.frames_total == 0:
        return None
    session = VisionSession(
        astronaut_id=astronaut_id,
        session_type="bitacora",
        module_id=settings.cameras.get(camera, f"cam{camera}"),
        source=f"vision:cam{camera}",
        started_at=started_at,
        ended_at=datetime.now(UTC),
        quality=quality_of(metrics.valid_frame_ratio),
        valid_frame_ratio=round(metrics.valid_frame_ratio, 3),
        identity=Identity(method="manual"),
        neutral_ok=True,
        fatigue=metrics.fatigue(),
        tension=metrics.tension(),
    )
    sink.send("/wellbeing/vision-sessions", session)
    return session
