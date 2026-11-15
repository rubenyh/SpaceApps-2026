"""Daily video log at a controlled distance (~50 cm): 3 s neutral of the day, then fatigue and
tension live, then one summary. Frames stay in memory only; only derived numbers leave."""

import csv
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

from wellbeing_vision.capture import open_camera
from wellbeing_vision.config import Settings
from wellbeing_vision.download import model_path
from wellbeing_vision.face import (
    EYE_CLOSED_RATIO, LEFT_EYE, MIN_VALID_S, NOD_PITCH_DEG, RIGHT_EYE, YAWN_JAW_DELTA, FaceFrame, SessionMetrics,
    face_frame, neutral_of,
)
from wellbeing_vision.facecrop import CROP_PX, FaceCrop
from wellbeing_vision.overlay import AMBER, WHITE, Notice, Row, render, severity
from wellbeing_vision.schemas import Identity, VisionSession
from wellbeing_vision.sink import Sink

NEUTRAL_S = 3.0
NEUTRAL_TIMEOUT_S = 30.0
WINDOW = "Bitacora - wellbeing-vision"
LANDMARKS_SHOWN = (*RIGHT_EYE, *LEFT_EYE, 13, 14, 61, 291)
FOOTER = "Umbrales provisionales · no se guarda video"
# Display-only marks for the live bars. PROVISIONAL, no clinical source.
PERCLOS_MARK = 0.15
TENSION_MARK = 0.20
TRACE_FIELDS = ("t", "face_px", "usable", "ear_ratio", "eye_blink", "jaw_delta", "brow_delta", "lip_delta")


def quality_of(valid_frame_ratio: float) -> str:
    # PROVISIONAL: share of frames with a usable face (too far counts as not usable).
    return "good" if valid_frame_ratio >= 0.8 else "suspect" if valid_frame_ratio >= 0.5 else "bad"


def _ema(prev: float | None, x: float, a: float) -> float:
    return x if prev is None else prev + a * (x - prev)


def live_sections(m: SessionMetrics, live: dict[str, float]) -> list[tuple[str, list[Row]]]:
    """Rows for the panel. live holds smoothed values relative to the neutral (empty = no face yet)."""
    def row(label, key, fmt, mark, scale, higher_is_worse=True):
        v = live.get(key)
        if v is None:
            return Row(label, "—", WHITE, 0.0, mark / scale)
        shown = max(v, 0.0)
        return Row(label, fmt(v), severity(shown, mark, higher_is_worse), shown / scale, mark / scale)

    pct = lambda v: f"{v * 100:.0f} %"  # noqa: E731
    fatigue = [
        row("Apertura de ojos", "eyes", pct, EYE_CLOSED_RATIO, 1.2, higher_is_worse=False),
        row("PERCLOS (ojos cerrados)", "perclos", pct, PERCLOS_MARK, 0.30),
        Row("Parpadeos", f"{m.blinks.count / (m.valid_s / 60):.0f} /min" if m.valid_s >= MIN_VALID_S else "—"),
        row("Inclinación de cabeza", "pitch", lambda v: f"{v:+.0f}°", NOD_PITCH_DEG, 30.0),
        Row("Cabeceos", str(m.nods.count)),
        row("Apertura de boca", "mouth", pct, YAWN_JAW_DELTA, 0.70),
        Row("Bostezos", str(m.yawns.count)),
    ]
    tension = [
        row("Cejo fruncido", "brow", pct, TENSION_MARK, 0.40),
        row("Labios apretados", "lip", pct, TENSION_MARK, 0.40),
    ]
    return [("FATIGA", fatigue), ("TENSIÓN", tension)]


def _landmarker(settings: Settings) -> FaceLandmarker:
    return FaceLandmarker.create_from_options(FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path(settings.models_dir, "face_landmarker.task"))),
        running_mode=RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    ))


def _detect(landmarker: FaceLandmarker, cropper: FaceCrop, frame: np.ndarray, t: float, ts_ms: int):
    """Landmarks on the face crop, reprojected to frame pixels. Returns (FaceFrame, xy) or (None, None)."""
    c = cropper.crop(frame)
    if c is None:
        return None, None
    crop, ox, oy, k = c
    res = landmarker.detect_for_video(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), ts_ms
    )
    if not res.face_landmarks:
        cropper.follow(None)
        return None, None
    xy = np.array([(p.x * CROP_PX / k + ox, p.y * CROP_PX / k + oy) for p in res.face_landmarks[0]])
    cropper.follow(xy)
    return face_frame(t, xy, res.face_blendshapes[0], res.facial_transformation_matrixes[0]), xy


def _far_notice(ff: FaceFrame, min_px: float) -> Notice:
    return Notice("Acércate a la cámara", f"Rostro {ff.face_px:.0f} px · mínimo {min_px:.0f} px (~50 cm)", AMBER)


NO_FACE = Notice("No se detecta el rostro", "Colócate de frente a la cámara", AMBER)


def run_bitacora(settings: Settings, sink: Sink, astronaut_id: str, camera: int, seconds: float,
                 mirror: bool = True, trace: Path | None = None) -> VisionSession | None:
    landmarker = _landmarker(settings)
    cropper = FaceCrop(model_path(settings.models_dir, "face_detection_yunet_2023mar.onnx"))
    cap = open_camera(camera)
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    title = f"BITÁCORA · {settings.astronauts.get(astronaut_id, astronaut_id)}"
    min_px = settings.min_face_px
    t0, last_ms, fullscreen = time.monotonic(), -1, False
    neutral_frames: list[FaceFrame] = []
    metrics: SessionMetrics | None = None
    live: dict[str, float] = {}
    started_at = rec_t0 = None
    trace_file = trace.open("w", newline="", encoding="utf-8") if trace else None
    tracer = csv.writer(trace_file) if trace_file else None
    if tracer:
        tracer.writerow(TRACE_FIELDS)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera stopped delivering frames.")
                break
            if mirror:
                frame = cv2.flip(frame, 1)  # metrics average both eyes, so mirroring does not change them
            t = time.monotonic() - t0
            last_ms = max(int(t * 1000), last_ms + 1)
            h, w = frame.shape[:2]
            ff, xy = _detect(landmarker, cropper, frame, t, last_ms)
            points = [(xy[i][0] / w, xy[i][1] / h) for i in LANDMARKS_SHOWN] if xy is not None else []
            # Too far: eye landmarks are too coarse for blinks, so the frame counts as not usable.
            usable = ff if ff and ff.face_px >= min_px else None
            notice = None if usable else _far_notice(ff, min_px) if ff else NO_FACE

            if metrics is None:
                # The neutral must be continuous and close enough: anything else restarts it.
                neutral_frames = neutral_frames + [usable] if usable else []
                held = neutral_frames[-1].t - neutral_frames[0].t if neutral_frames else 0.0
                notice = notice or Notice("Mantén el rostro relajado", "Mira a la cámara · neutral del día",
                                          progress=held / NEUTRAL_S)
                canvas = render(frame, title, "CALIBRANDO", [("Las métricas aparecen al calibrar", [])],
                                FOOTER, notice, points)
                if held >= NEUTRAL_S:
                    metrics = SessionMetrics(neutral_of(neutral_frames))
                    started_at, rec_t0 = datetime.now(UTC), t
                elif t > NEUTRAL_TIMEOUT_S:
                    print("Calibration failed: no steady, close face for 3 s. No summary sent.")
                    break
            else:
                metrics.add(usable, t)
                n = metrics.neutral
                if usable:
                    live["eyes"] = _ema(live.get("eyes"), usable.ear / n.ear if n.ear else 0.0, 0.1)
                    live["pitch"] = _ema(live.get("pitch"), usable.pitch - n.pitch, 0.3)
                    live["mouth"] = _ema(live.get("mouth"), max(0.0, usable.jaw_open - n.jaw_open), 0.3)
                    live["brow"] = _ema(live.get("brow"), max(0.0, usable.brow_down - n.brow_down), 0.2)
                    live["lip"] = _ema(live.get("lip"), max(0.0, usable.lip_press - n.lip_press), 0.2)
                if metrics.valid_s >= MIN_VALID_S:  # same rule as the summary: too short is not measurable
                    live["perclos"] = metrics.closed_s / metrics.valid_s
                if tracer and ff:
                    tracer.writerow([f"{t:.3f}", f"{ff.face_px:.0f}", int(usable is not None),
                                     f"{ff.ear / n.ear:.3f}", f"{ff.eye_blink:.3f}", f"{ff.jaw_open - n.jaw_open:.3f}",
                                     f"{ff.brow_down - n.brow_down:.3f}", f"{ff.lip_press - n.lip_press:.3f}"])
                left = max(0.0, seconds - (t - rec_t0))
                status = f"GRABANDO · {int(left) // 60}:{int(left) % 60:02d} restante"
                canvas = render(frame, title, status, live_sections(metrics, live), FOOTER, notice, points)
                if t - rec_t0 >= seconds:
                    break

            cv2.imshow(WINDOW, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("f"):
                fullscreen = not fullscreen
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        if trace_file:
            trace_file.close()

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
