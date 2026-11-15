"""Face enrollment and the multi-person identity preview. Frames stay in memory; only templates are saved."""

import time

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

from wellbeing_vision.capture import open_configured
from wellbeing_vision.config import Settings
from wellbeing_vision.download import model_path
from wellbeing_vision.identity import MATCH, ORIENTATIONS, FaceID, Gallery, rotate, unrotate
from wellbeing_vision.overlay import AMBER, GREEN, MUTED, Notice, Row, render
from wellbeing_vision.tracker import IoUTracker, resolve

ENROLL_SAMPLES = 10
ENROLL_GAP_S = 0.3  # spread the samples so small head turns end up in the gallery
ENROLL_MIN_SCORE = 0.9  # YuNet confidence for an enrollment sample
ENROLL_TIMEOUT_S = 60.0
FOOTER = "Templates stay on this computer · no video is stored"
# Upper body only: the crew sits at a table.
POSE_MAX_SIDE = 640  # the pose model works at 256 px: a bigger copy only costs conversion time
SKELETON = ((11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24))


def face_id(settings: Settings) -> FaceID:
    return FaceID(model_path(settings.models_dir, "face_detection_yunet_2023mar.onnx"),
                  model_path(settings.models_dir, "face_recognition_sface_2021dec.onnx"))


def gallery_of(settings: Settings) -> Gallery:
    return Gallery(settings.data_dir / "faces").load(settings.astronauts)


class _Window:
    """Preview window: f toggles fullscreen, q/Esc or closing the window ends."""

    def __init__(self, name: str) -> None:
        self.name, self.fullscreen = name, False
        cv2.namedWindow(name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    def show(self, canvas: np.ndarray) -> bool:
        cv2.imshow(self.name, canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("f"):
            self.fullscreen = not self.fullscreen
            cv2.setWindowProperty(self.name, cv2.WND_PROP_FULLSCREEN,
                                  cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL)
        return key not in (ord("q"), 27) and cv2.getWindowProperty(self.name, cv2.WND_PROP_VISIBLE) >= 1


def run_enroll(settings: Settings, astronaut_id: str, camera: int, samples: int = ENROLL_SAMPLES) -> bool:
    """Shows the frame as the camera delivers it: only the daily log mirrors (self-view)."""
    faceid, gallery = face_id(settings), gallery_of(settings)
    cap, window = open_configured(camera, settings), _Window("Enrollment - wellbeing-vision")
    title = f"ENROLLMENT · {settings.astronauts.get(astronaut_id, astronaut_id)}"
    templates: list[np.ndarray] = []
    t0, last = time.monotonic(), -ENROLL_GAP_S
    try:
        while len(templates) < samples and time.monotonic() - t0 < ENROLL_TIMEOUT_S:
            ok, raw = cap.read()
            if not ok:
                print("Camera stopped delivering frames.")
                break
            t = time.monotonic() - t0
            faces = faceid.detect(raw, (0,))  # enroll upright; SFace alignment covers other orientations
            if len(faces) != 1:
                notice = Notice("Only the person enrolling in view" if faces else "No face detected",
                                "One face, looking at the camera", AMBER)
            elif faces[0].width < settings.min_face_px:
                notice = Notice("Move closer to the camera", f"Face {faces[0].width:.0f} px · minimum "
                                f"{settings.min_face_px:.0f} px (~50 cm)", AMBER)
            else:
                if faces[0].row[14] >= ENROLL_MIN_SCORE and t - last >= ENROLL_GAP_S:
                    templates.append(faceid.template(raw, faces[0]))
                    last = t
                notice = Notice("Look at the camera", f"Sample {len(templates)}/{samples} · turn your head a "
                                "little", progress=len(templates) / samples)
            if not window.show(render(raw, title, "ENROLLING", [], FOOTER, notice)):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    if len(templates) < samples:
        print(f"Enrollment incomplete ({len(templates)}/{samples} samples). Nothing saved.")
        return False
    mean = np.mean(templates, axis=0)
    others = {i: s for i, s in gallery.scores(mean / np.linalg.norm(mean)).items() if i != astronaut_id}
    for i, s in others.items():
        if s >= MATCH:
            print(f"Warning: this face also matches {i} ({s:.2f}). Check who is enrolled as whom.")
    gallery.enroll(astronaut_id, templates)
    print(f"Enrolled {astronaut_id}: {samples} templates in {gallery.dir / (astronaut_id + '.npz')}")
    return True


def _pose_landmarker(settings: Settings) -> PoseLandmarker:
    return PoseLandmarker.create_from_options(PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path(settings.models_dir, "pose_landmarker_lite.task"))),
        running_mode=RunningMode.VIDEO,
        num_poses=4,
    ))


def detect_poses(pose: PoseLandmarker, frame: np.ndarray, deg: int, ts_ms: int) -> list[np.ndarray]:
    """Poses found in the frame rotated like the faces, as 33 x (x, y, visibility) in frame pixels.
    Runs on a copy of at most POSE_MAX_SIDE px; landmarks are normalized, so they map back to full size."""
    h, w = frame.shape[:2]
    k = min(1.0, POSE_MAX_SIDE / max(w, h))
    small = cv2.resize(frame, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA) if k < 1 else frame
    img = rotate(small, deg)
    res = pose.detect_for_video(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts_ms)
    ih, iw = (w, h) if deg in (90, 270) else (h, w)  # full-resolution size of the rotated frame
    return [np.column_stack([unrotate(np.array([(p.x * iw, p.y * ih) for p in lm]), deg, w, h),
                             [p.visibility for p in lm]]) for lm in res.pose_landmarks]


def skeleton(pose: np.ndarray, w: float, h: float) -> list:
    """Visible upper-body segments, normalized to the frame."""
    p = lambda i: (pose[i][0] / w, pose[i][1] / h)  # noqa: E731
    return [(p(a), p(b)) for a, b in SKELETON if min(pose[a][2], pose[b][2]) > 0.5]


def run_identify(settings: Settings, camera: int, seconds: float = 0.0, rotation: int | None = None) -> None:
    """Live preview: who is in view, one box per tracked face, the pose linked to it. Sends nothing.
    The frame is shown as the camera delivers it: rotation is only tried internally to find faces."""
    faceid, gallery, tracker = face_id(settings), gallery_of(settings), IoUTracker()
    if not gallery.people:
        print("No enrolled faces: everyone shows as unknown. Run: wellbeing-vision enroll --astronaut ast-01")
    orientations = (rotation,) if rotation is not None else ORIENTATIONS
    faceid.deg = orientations[0]
    pose = _pose_landmarker(settings)
    cap, window = open_configured(camera, settings), _Window("Identity - wellbeing-vision")
    t0, last_ms = time.monotonic(), -1
    names: dict[str, float] = {}
    try:
        while not seconds or time.monotonic() - t0 < seconds:
            ok, frame = cap.read()
            if not ok:
                print("Camera stopped delivering frames.")
                break
            h, w = frame.shape[:2]
            faces = faceid.detect(frame, orientations)
            t = time.monotonic() - t0
            last_ms = max(int(t * 1000), last_ms + 1)
            seen = tracker.update(faces, t, detect_poses(pose, frame, faceid.deg, last_ms))
            for tr in seen:
                if gallery.people and tr.needs_template(t):
                    tr.vote(gallery.scores(faceid.template(frame, tr.face)), t)
            resolve(seen)

            boxes, lines, rows = [], [], []
            for tr in sorted(seen, key=lambda tr: tr.id):
                name = settings.astronauts.get(tr.astronaut, tr.astronaut) if tr.astronaut else tr.label
                color = GREEN if tr.astronaut else AMBER
                x0, y0, x1, y1 = tr.box  # face, or the body while the face is not seen
                boxes.append((x0 / w, y0 / h, x1 / w, y1 / h, name, color))
                if tr.pose is not None:
                    lines += skeleton(tr.pose, w, h)
                rows.append(Row(name, f"{tr.score:.2f}" if tr.votes else "—", color))
                if tr.astronaut:
                    names[name] = max(names.get(name, 0.0), tr.score)
            rows.append(Row("Orientation", f"{faceid.deg}°", MUTED))
            status = f"{len(seen)} in view" if seen else "Nobody in view"
            if not window.show(render(frame, "IDENTITY", status, [("CREW IN VIEW", rows)], FOOTER,
                                      boxes=boxes, lines=lines)):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        pose.close()
    print("Recognized:", ", ".join(f"{n} ({s:.2f})" for n, s in names.items()) or "nobody")
