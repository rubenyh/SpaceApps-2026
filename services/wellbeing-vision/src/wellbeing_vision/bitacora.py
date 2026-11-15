"""Daily video log at a controlled distance (~50 cm): 3 s neutral of the day, then fatigue and
tension live, then one summary. Frames stay in memory only; only derived numbers leave."""

import csv
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

from wellbeing_vision.anchor import anchor_file, load_anchor, save_neutral
from wellbeing_vision.capture import open_camera
from wellbeing_vision.config import Settings
from wellbeing_vision.download import model_path
from wellbeing_vision.face import (
    LEFT_EYE, MIN_VALID_S, NOD_PITCH_DEG, RIGHT_EYE, YAWN_JAW_DELTA, FaceFrame, SessionMetrics, calibration_break,
    face_frame, neutral_of, neutral_problem,
)
from wellbeing_vision.facecrop import CROP_PX, FaceCrop
from wellbeing_vision.identify import face_id, gallery_of
from wellbeing_vision.identity import face_verdict, verify
from wellbeing_vision.overlay import AMBER, MUTED, RED, WHITE, Notice, Row, render, severity
from wellbeing_vision.schemas import VisionSession
from wellbeing_vision.sink import Sink

NEUTRAL_S = 3.0
NEUTRAL_TIMEOUT_S = 45.0
CALIB_HINTS = {
    "blink": "You blinked · keep your eyes open for 3 s",
    "move": "Keep your head still",
    "mouth": "Do not talk during calibration",
    "squint": "Open your eyes normally",
    "anchor": "Different from your usual neutral · relax your face",
    "gaze": "Look at the camera",
}
WINDOW = "Daily log - wellbeing-vision"
LANDMARKS_SHOWN = (*RIGHT_EYE, *LEFT_EYE, 13, 14, 61, 291)
FOOTER = "Provisional thresholds · no video is stored"
# Display-only marks for the live bars. PROVISIONAL, no clinical source.
EYES_MARK = 0.6
PERCLOS_MARK = 0.15
TENSION_MARK = 0.20
ID_EVERY = 10  # frames between face templates for the identity check
MIN_ID_SAMPLES = 3  # face samples before the preview says the face belongs to someone else
STALL_S = 2.0  # a gap between processed frames this long ends the log (camera or window stalled)
TRACE_FIELDS = ("t", "face_px", "usable", "ear", "ear_ratio", "eye_blink", "jaw_delta", "brow_delta", "lip_delta",
                "speaking", "pitch_delta", "yaw", "look_down_delta", "look_up_delta", "looking_down")


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
        row("Eye openness", "eyes", pct, EYES_MARK, 1.2, higher_is_worse=False),
        row("PERCLOS (eyes closed)", "perclos", pct, PERCLOS_MARK, 0.30),
        Row("Blinks", f"{m.blinks.count / (m.valid_s / 60):.0f} /min" if m.valid_s >= MIN_VALID_S else "—"),
        row("Head tilt", "pitch", lambda v: f"{v:+.0f}°", NOD_PITCH_DEG, 30.0),
        Row("Nods", str(m.nods.count)),
        row("Mouth opening", "mouth", pct, YAWN_JAW_DELTA, 0.70),
        Row("Yawns", str(m.yawns.count)),
    ]
    tension = [
        row("Brow lowering", "brow", pct, TENSION_MARK, 0.40),
        Row("Lip press", "talking", MUTED) if live.get("speaking")
        else row("Lip press", "lip", pct, TENSION_MARK, 0.40),
    ]
    return [("FATIGUE", fatigue), ("TENSION", tension)]


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


def _unused(path: Path) -> Path:
    """--trace never overwrites a previous session: t.csv, then t-2.csv, t-3.csv..."""
    candidate, n = path, 2
    while candidate.exists():
        candidate, n = path.with_stem(f"{path.stem}-{n}"), n + 1
    if candidate != path:
        print(f"{path} exists: tracing to {candidate}")
    return candidate


def _far_notice(ff: FaceFrame, min_px: float) -> Notice:
    return Notice("Move closer to the camera", f"Face {ff.face_px:.0f} px · minimum {min_px:.0f} px (~50 cm)", AMBER)


NO_FACE = Notice("No face detected", "Face the camera", AMBER)
LOOK_DOWN = Notice("Look at the camera", "Looking down is not measured", AMBER)


def run_bitacora(settings: Settings, sink: Sink, astronaut_id: str, camera: int, seconds: float,
                 mirror: bool = True, trace: Path | None = None) -> VisionSession | None:
    landmarker = _landmarker(settings)
    cropper = FaceCrop(model_path(settings.models_dir, "face_detection_yunet_2023mar.onnx"))
    faceid, gallery = face_id(settings), gallery_of(settings)
    id_samples = []  # (scores, template) from the recording, for the identity check
    cap = open_camera(camera)
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    title = f"DAILY LOG · {settings.astronauts.get(astronaut_id, astronaut_id)}"
    min_px = settings.min_face_px
    t0, last_ms, fullscreen = time.monotonic(), -1, False
    neutral_frames: list[FaceFrame] = []
    anchor_path = anchor_file(settings.data_dir, astronaut_id)
    anchor, anchor_n = load_anchor(anchor_path)
    day_neutral, retried, used_anchor, why, why_t = None, False, False, None, 0.0
    metrics: SessionMetrics | None = None
    live: dict[str, float] = {}
    started_at = rec_t0 = last_t = mismatch = None
    trace = _unused(trace) if trace else None
    trace_file = trace.open("w", newline="", encoding="utf-8") if trace else None
    tracer = csv.writer(trace_file) if trace_file else None
    if tracer:
        tracer.writerow(TRACE_FIELDS)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera stopped delivering frames: the log ends at the last frame.")
                break
            raw = frame  # identity uses the unmirrored face, like the enrollment
            if mirror:
                frame = cv2.flip(frame, 1)  # metrics average both eyes, so mirroring does not change them
            t = time.monotonic() - t0
            if last_t is not None and t - last_t > STALL_S:
                print(f"No frame for {t - last_t:.0f} s (camera or window stalled): the log ends at the last frame.")
                break
            last_ms = max(int(t * 1000), last_ms + 1)
            h, w = frame.shape[:2]
            ff, xy = _detect(landmarker, cropper, frame, t, last_ms)
            points = [(xy[i][0] / w, xy[i][1] / h) for i in LANDMARKS_SHOWN] if xy is not None else []
            # Too far: eye landmarks are too coarse for blinks, so the frame counts as not usable.
            usable = ff if ff and ff.face_px >= min_px else None
            notice = None if usable else _far_notice(ff, min_px) if ff else NO_FACE

            if metrics is None:
                # Steady, close and relaxed for 3 s in a row; a blink, head move or talking restarts it.
                broke = calibration_break(neutral_frames, usable) if usable else None
                if broke:
                    why, why_t = broke, t
                neutral_frames = [usable] if broke else neutral_frames + [usable] if usable else []
                held = neutral_frames[-1].t - neutral_frames[0].t if neutral_frames else 0.0
                if held >= NEUTRAL_S:
                    day_neutral = neutral_of(neutral_frames)
                    problem = neutral_problem(day_neutral, anchor)
                    if problem == "squint" or (problem == "anchor" and not retried):
                        retried = retried or problem == "anchor"
                        why, why_t, neutral_frames = problem, t, []
                    else:
                        # Off the anchor twice in a row: the day's eyes are not trusted, the anchor's are.
                        used_anchor = problem == "anchor"
                        neutral = (replace(day_neutral, ear=anchor.ear, eye_blink=anchor.eye_blink)
                                   if used_anchor else day_neutral)
                        metrics = SessionMetrics(neutral)
                        started_at, rec_t0 = datetime.now(UTC), t
                hint = CALIB_HINTS[why] if why and t - why_t < 2.5 else "Look at the camera · today's neutral"
                notice = notice or Notice("Keep your face relaxed", hint, progress=held / NEUTRAL_S)
                canvas = render(frame, title, "CALIBRATING", [("Metrics appear after calibration", [])],
                                FOOTER, notice, points)
                if metrics is None and t > NEUTRAL_TIMEOUT_S:
                    print("Calibration failed: no steady, relaxed, close face for 3 s. No summary sent.")
                    break
            else:
                metrics.add(usable, t)
                last_t = t
                if gallery.people and metrics.frames_total % ID_EVERY == 0:
                    faces = faceid.detect(raw)
                    if faces:
                        face = max(faces, key=lambda f: f.width)
                        tpl = faceid.template(raw, face)
                        id_samples.append((gallery.scores(tpl), tpl))
                        who = face_verdict(id_samples)[0] if len(id_samples) >= MIN_ID_SAMPLES else None
                        mismatch = who if who and who != astronaut_id else None
                n = metrics.neutral
                if mismatch:
                    notice = Notice(f"This looks like {mismatch}, not {astronaut_id}", "This log will not be sent", RED)
                elif usable and metrics.looking_down:
                    notice = LOOK_DOWN
                elif usable:
                    live["eyes"] = _ema(live.get("eyes"), usable.ear / n.ear if n.ear else 0.0, 0.1)
                    live["pitch"] = _ema(live.get("pitch"), usable.pitch - n.pitch, 0.3)
                    live["mouth"] = _ema(live.get("mouth"), max(0.0, usable.jaw_open - n.jaw_open), 0.3)
                    live["brow"] = _ema(live.get("brow"), max(0.0, usable.brow_down - n.brow_down), 0.2)
                    if not metrics.speaking:
                        live["lip"] = _ema(live.get("lip"), max(0.0, usable.lip_press - n.lip_press), 0.2)
                live["speaking"] = metrics.speaking
                if metrics.valid_s >= MIN_VALID_S:  # same rule as the summary: too short is not measurable
                    live["perclos"] = metrics.closed_s / metrics.valid_s
                if tracer and ff:
                    tracer.writerow([f"{t:.3f}", f"{ff.face_px:.0f}", int(usable is not None), f"{ff.ear:.4f}",
                                     f"{ff.ear / n.ear:.3f}", f"{ff.eye_blink:.3f}", f"{ff.jaw_open - n.jaw_open:.3f}",
                                     f"{ff.brow_down - n.brow_down:.3f}", f"{ff.lip_press - n.lip_press:.3f}",
                                     int(metrics.speaking), f"{ff.pitch - n.pitch:.1f}", f"{ff.yaw:.1f}",
                                     f"{ff.look_down - n.look_down:.3f}", f"{ff.look_up - n.look_up:.3f}",
                                     int(metrics.looking_down)])
                left = max(0.0, seconds - (t - rec_t0))
                status = f"RECORDING · {int(left) // 60}:{int(left) % 60:02d} left"
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
    identity, new_templates, id_msg = verify(id_samples, astronaut_id)
    print(f"Identity: {id_msg}")
    if identity is None:  # someone else's face: never store it under the declared astronaut
        return None
    session = VisionSession(
        astronaut_id=astronaut_id,
        session_type="bitacora",
        module_id=settings.cameras.get(camera, f"cam{camera}"),
        source=f"vision:cam{camera}",
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=last_t - rec_t0),  # last processed frame, not wall clock
        quality=quality_of(metrics.valid_frame_ratio),
        valid_frame_ratio=round(metrics.valid_frame_ratio, 3),
        identity=identity,
        neutral_ok=True,
        fatigue=metrics.fatigue(),
        tension=metrics.tension(),
    )
    sink.send("/wellbeing/vision-sessions", session)
    save_neutral(anchor_path, day_neutral)
    if new_templates:
        gallery.add_auto(astronaut_id, new_templates)
    measured = metrics.talking_s + metrics.quiet_s
    talk = metrics.talking_s / measured if measured else 0.0
    print(f"Talking {talk:.0%} of valid time (excluded from lip press; null below {MIN_VALID_S:.0f} s quiet)")
    ref = "anchor (today's neutral was off twice)" if used_anchor else "today's neutral"
    print(f"Eye reference: {ref}; anchor from {anchor_n} past neutrals"
          f"{'' if anchor else ' (needs 3)'}; neutral eyeBlink {day_neutral.eye_blink:.2f}, EAR {day_neutral.ear:.3f}")
    return session
