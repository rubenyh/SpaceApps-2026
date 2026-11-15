"""Ambient mode: one camera per module (cam 0 = modulo-a, cam 1 = modulo-b), all in one process.

Every window (60 s) each module sends one co-presence record and one ambient session (motion) per person.
Identity is resolved across cameras, so one astronaut is in one module at a time; seeing them in the other
module is a transfer. Frames stay in memory; only derived numbers leave.
"""

import itertools
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np

from wellbeing_vision.capture import open_camera
from wellbeing_vision.config import Settings
from wellbeing_vision.identify import _pose_landmarker, _Window, detect_poses, face_id, gallery_of, skeleton
from wellbeing_vision.identity import ORIENTATIONS
from wellbeing_vision.motion import ModuleWindow
from wellbeing_vision.overlay import AMBER, GREEN, MUTED, Row, render
from wellbeing_vision.sink import Sink
from wellbeing_vision.tracker import IoUTracker, link_poses, resolve

MAX_DT_S = 0.5  # cap per-frame time so a slow frame does not inflate presence
MIN_PARTIAL_S = 10.0  # a window cut short by quitting is still sent if it lasted this long
TILE = (640, 360)  # each camera in the stacked preview
FOOTER = "Provisional thresholds · no video is stored"


class _Module:
    """One camera = one module: its own detector state, tracker, pose model and current window."""

    def __init__(self, settings: Settings, index: int, ids, rotation: int | None, start: datetime) -> None:
        self.index, self.module_id = index, settings.cameras.get(index, f"cam{index}")
        self.source = f"vision:cam{index}"
        self.camera = open_camera(index)
        self.faceid, self.tracker, self.pose = face_id(settings), IoUTracker(ids), _pose_landmarker(settings)
        self.orientations = (rotation,) if rotation is not None else ORIENTATIONS
        self.faceid.deg = self.orientations[0]
        self.window = ModuleWindow(self.module_id, self.source, start)
        self.labels: dict[int, str] = {}  # track id -> astronaut or unknown-<id>, last known
        self.seen, self.frame, self.last_t, self.i, self.last_ms, self.fps = [], None, None, 0, -1, 0.0

    def detect(self, gallery) -> bool:
        ok, frame = self.camera.read()
        if not ok:
            print(f"Camera {self.index} ({self.module_id}) stopped delivering frames.")
            return False
        self.frame, self.i = frame, self.i + 1
        self.seen = self.tracker.update(self.faceid.detect(frame, self.orientations), self.i)
        for tr in self.seen:
            if gallery.people and tr.needs_template(self.i):
                tr.vote(gallery.scores(self.faceid.template(frame, tr.face)), self.i)
        return True

    def measure(self, t: float) -> None:
        """After identities are resolved across cameras: poses, then this frame into the window."""
        dt = min(t - self.last_t, MAX_DT_S) if self.last_t is not None else 0.0
        if self.last_t is not None and t > self.last_t:
            self.fps = 0.9 * self.fps + 0.1 / (t - self.last_t) if self.fps else 1 / (t - self.last_t)
        self.last_t = t
        self.last_ms = max(int(t * 1000), self.last_ms + 1)
        link_poses(self.seen, detect_poses(self.pose, self.frame, self.faceid.deg, self.last_ms))
        for tr in self.seen:
            self.labels[tr.id] = tr.label
        self.window.add(dt, {tr.id: tr.pose for tr in self.seen})

    def close(self) -> None:
        self.camera.release()
        self.pose.close()


def _flush(modules: list[_Module], sink: Sink, scores: dict[str, float], end: datetime) -> int:
    sent = 0
    for m in modules:
        co, sessions = m.window.flush(m.labels, scores, end)
        if co:
            sink.send("/wellbeing/co-presence", co)
            sent += 1
        for s in sessions:
            sink.send("/wellbeing/vision-sessions", s)
            sent += 1
        print(f"{m.module_id} {m.window.start.astimezone():%H:%M:%S}-{end.astimezone():%H:%M:%S}: "
              f"{', '.join(f'{o.astronaut_id} {o.seconds_present:.0f}s' for o in co.occupants) if co else 'empty'}; "
              f"{len(co.pairs) if co else 0} pairs, {len(sessions)} motion sessions")
        m.window = ModuleWindow(m.module_id, m.source, end)
    return sent


def run_ambiente(settings: Settings, sink: Sink, cameras: list[int], window_s: float = 60.0,
                 rotation: int | None = None, seconds: float = 0.0) -> None:
    gallery = gallery_of(settings)
    if not gallery.people:
        print("No enrolled faces: everyone shows as unknown-<n>. Run: wellbeing-vision enroll --astronaut ast-01")
    ids, start = itertools.count(1), datetime.now(UTC)
    t0 = time.monotonic()
    modules = [_Module(settings, i, ids, rotation, start) for i in cameras]
    window_t0, window = 0.0, _Window("Ambient - wellbeing-vision")
    where: dict[str, str] = {}  # astronaut -> module last seen in
    transfers: list[str] = []
    scores: dict[str, float] = {}
    sent, n = 0, len(modules)
    pool = ThreadPoolExecutor(max_workers=n)  # OpenCV and MediaPipe release the GIL: cameras run in parallel
    try:
        while not seconds or time.monotonic() - t0 < seconds:
            if not all(pool.map(lambda m: m.detect(gallery), modules)):
                break
            resolve([tr for m in modules for tr in m.seen])  # one astronaut, one face, across modules
            t = time.monotonic() - t0
            list(pool.map(lambda m: m.measure(t), modules))
            for m in modules:
                for tr in m.seen:
                    if tr.astronaut:
                        scores[tr.astronaut] = tr.score
                        if where.get(tr.astronaut, m.module_id) != m.module_id:
                            event = f"{tr.astronaut}: {where[tr.astronaut]} -> {m.module_id}"
                            transfers = (transfers + [f"{datetime.now():%H:%M:%S} {event}"])[-3:]
                            print("Transfer", event)
                        where[tr.astronaut] = m.module_id
            if t - window_t0 >= window_s:
                sent += _flush(modules, sink, scores, start + timedelta(seconds=t))
                window_t0 = t

            # Preview: cameras stacked top to bottom, as delivered (no mirror, no rotation).
            tiles, boxes, lines, sections = [], [], [], []
            for k, m in enumerate(modules):
                h, w = m.frame.shape[:2]
                tiles.append(cv2.resize(m.frame, TILE))
                rows = []
                for tr in sorted(m.seen, key=lambda tr: tr.id):
                    name = settings.astronauts.get(tr.astronaut, tr.astronaut) if tr.astronaut else tr.label
                    color = GREEN if tr.astronaut else AMBER
                    x0, y0, x1, y1 = tr.face.box
                    boxes.append((x0 / w, (k + y0 / h) / n, x1 / w, (k + y1 / h) / n, name, color))
                    if tr.pose is not None:  # each camera takes 1/n of the stacked preview's height
                        lines += [((a[0], (k + a[1]) / n), (b[0], (k + b[1]) / n)) for a, b in skeleton(tr.pose, w, h)]
                for label, s in m.window.present(m.labels).items():
                    rows.append(Row(settings.astronauts.get(label, label), f"{s:.0f} s",
                                    GREEN if not label.startswith("unknown-") else AMBER))
                together = {}
                for (a, b), p in m.window.pairs.items():
                    key = " + ".join(sorted((m.labels.get(a, f"unknown-{a}"), m.labels.get(b, f"unknown-{b}"))))
                    together[key] = together.get(key, 0.0) + p.together_s
                rows += [Row(k_, f"{s:.0f} s together", MUTED) for k_, s in together.items()]
                where_txt = "top" if k == 0 and n > 1 else "bottom" if n > 1 else "view"
                sections.append((f"{m.module_id.upper()} · CAM {m.index} ({where_txt}) · {m.fps:.0f} FPS",
                                 rows or [Row("Nobody in view", "", MUTED)]))
            if transfers:
                sections.append(("TRANSFERS", [Row(e, "", MUTED) for e in transfers]))
            left = max(0.0, window_s - (t - window_t0))
            status = f"WINDOW {int(left) // 60}:{int(left) % 60:02d} · {sent} sent"
            if not window.show(render(np.vstack(tiles), "AMBIENT", status, sections, FOOTER,
                                      boxes=boxes, lines=lines)):
                break
    finally:
        t = time.monotonic() - t0
        if t - window_t0 >= MIN_PARTIAL_S:
            sent += _flush(modules, sink, scores, start + timedelta(seconds=t))
        pool.shutdown()
        for m in modules:
            m.close()
        cv2.destroyAllWindows()
        print(f"Sent {sent} records. FPS per camera: "
              + ", ".join(f"cam{m.index} {m.i / t:.1f}" for m in modules if t > 0))
