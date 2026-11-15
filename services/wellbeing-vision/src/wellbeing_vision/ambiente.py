"""Ambient mode: one camera per module (cam 0 = modulo-a, cam 1 = modulo-b), all in one process.

Every window (60 s) each module sends one co-presence record and one ambient session (motion) per person.
Cameras are meant to watch different zones. If two cameras see the same astronaut at once, they stay in the
module they belong to (Homes) and the other camera shows them as "seen from <module>" without counting them
twice. With --overlap the cameras share one space and feed a single module. Frames stay in memory; only
derived numbers leave.
"""

import csv
import itertools
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from wellbeing_vision.bitacora import unused_path
from wellbeing_vision.capture import open_configured
from wellbeing_vision.config import Settings
from wellbeing_vision.identify import _pose_landmarker, _Window, detect_poses, face_id, gallery_of, skeleton
from wellbeing_vision.identity import ORIENTATIONS
from wellbeing_vision.motion import ModuleWindow, body
from wellbeing_vision.overlay import AMBER, GREEN, MUTED, Row, render
from wellbeing_vision.sink import Sink
from wellbeing_vision.tracker import IoUTracker, resolve

MAX_DT_S = 0.5  # cap per-frame time so a slow frame does not inflate presence
MIN_PARTIAL_S = 10.0  # a window cut short by quitting is still sent if it lasted this long
# PROVISIONAL. With 3 s / 3 s / 1 s the real trace amb3-2 had "a -> b" and "b -> a" 22 s apart; with these, one.
TRANSFER_GONE_S = 10.0  # a transfer needs the person unseen in the old module this long...
TRANSFER_HOLD_S = 5.0  # ...and seen steadily in the new one this long
SIGHTING_GAP_S = 2.0  # a longer gap restarts the "seen steadily" clock
MAX_PAIR_ROWS = 3
FOOTER = "Provisional thresholds · no video is stored"
TRACE_FIELDS = ("t", "module", "track", "label", "counted", "face", "pose", "shoulder_px", "head_turn_sw", "elsewhere")


class Homes:
    """The module each astronaut belongs to. A transfer needs them gone from the old module for
    TRANSFER_GONE_S and steadily in the new one for TRANSFER_HOLD_S; until then they stay where they were."""

    def __init__(self) -> None:
        self.home: dict[str, str] = {}
        self.last: dict[tuple[str, str], float] = {}  # (astronaut, module) -> last sighting
        self.since: dict[tuple[str, str], float] = {}  # (astronaut, module) -> start of the steady sighting

    def update(self, sightings: dict[str, set[str]], t: float) -> list[str]:
        """sightings: astronaut -> modules that see them at t. Returns the transfers that happened."""
        events = []
        for who, modules in sightings.items():
            for m in modules:
                if t - self.last.get((who, m), -1e9) > SIGHTING_GAP_S:
                    self.since[(who, m)] = t
                self.last[(who, m)] = t
            home = self.home.setdefault(who, min(modules))
            for m in sorted(modules - {home}):
                steady = t - self.since[(who, m)] >= TRANSFER_HOLD_S
                if steady and t - self.last.get((who, home), -1e9) >= TRANSFER_GONE_S:
                    events.append(f"{who}: {home} -> {m}")
                    self.home[who] = m
                    break
        return events

    def counted_in(self, who: str, modules: set[str]) -> str:
        """Of the modules seeing them right now, the one that counts them: home if it is one of them."""
        return self.home[who] if self.home.get(who) in modules else min(modules)


def assign(cams, homes: Homes, sightings: dict[str, set[str]]) -> None:
    """Each astronaut seen this frame is counted by one track only: the first one in the module that counts
    them. Every other track of that astronaut gets tr.elsewhere = that module and is not counted."""
    taken: set[str] = set()
    for c in cams:
        for tr in c.seen:
            if tr.astronaut:
                home = homes.counted_in(tr.astronaut, sightings[tr.astronaut])
                if c.module_id == home and tr.astronaut not in taken:
                    taken.add(tr.astronaut)
                else:
                    tr.elsewhere = home


class _Camera:
    """One camera: its own detector state, tracker and pose model."""

    def __init__(self, settings: Settings, index: int, module_id: str, ids, rotation: int | None) -> None:
        self.index, self.module_id = index, module_id
        self.camera = open_configured(index, settings, settings.ambient_width, settings.ambient_height)
        self.faceid, self.tracker, self.pose = face_id(settings), IoUTracker(ids), _pose_landmarker(settings)
        self.orientations = (rotation,) if rotation is not None else ORIENTATIONS
        self.faceid.deg = self.orientations[0]
        self.seen, self.frame, self.last_t, self.dt, self.frames, self.last_ms, self.fps = [], None, None, 0.0, 0, -1, 0.0

    def step(self, gallery, t0: float) -> bool:
        """Newest frame -> faces, poses, tracks, identity votes (new or unconfirmed tracks; re-check every 2 s)."""
        ok, frame = self.camera.read()
        if not ok:
            print(f"Camera {self.index} ({self.module_id}) stopped delivering frames.")
            return False
        t = time.monotonic() - t0
        if self.last_t is not None and t > self.last_t:
            self.fps = 0.9 * self.fps + 0.1 / (t - self.last_t) if self.fps else 1 / (t - self.last_t)
            self.dt = min(t - self.last_t, MAX_DT_S)
        self.frame, self.frames, self.last_t = frame, self.frames + 1, t
        faces = self.faceid.detect(frame, self.orientations)
        self.last_ms = max(int(t * 1000), self.last_ms + 1)
        self.seen = self.tracker.update(faces, t, detect_poses(self.pose, frame, self.faceid.deg, self.last_ms))
        for tr in self.seen:
            tr.elsewhere = None
            if gallery.people and tr.needs_template(t):
                tr.vote(gallery.scores(self.faceid.template(frame, tr.face)), t)
        resolve(self.seen)  # one astronaut per face within this camera
        return True

    def close(self) -> None:
        self.camera.release()
        self.pose.close()


def _flush(windows: dict[str, ModuleWindow], sink: Sink, labels, scores, end: datetime) -> int:
    sent = 0
    for key, w in windows.items():
        co, sessions = w.flush(labels, scores, end)
        if co:
            sink.send("/wellbeing/co-presence", co)
            sent += 1
        for s in sessions:
            sink.send("/wellbeing/vision-sessions", s)
            sent += 1
        print(f"{w.module_id} {w.start.astimezone():%H:%M:%S}-{end.astimezone():%H:%M:%S}: "
              f"{', '.join(f'{o.astronaut_id} {o.seconds_present:.0f}s' for o in co.occupants) if co else 'empty'}; "
              f"{len(co.pairs) if co else 0} pairs, {len(sessions)} motion sessions")
        windows[key] = ModuleWindow(w.module_id, w.source, end)
    return sent


def panel_rows(settings: Settings, window: ModuleWindow, labels: dict[int, str], also: list[str]) -> list[Row]:
    """Named people, the unknowns as one row, who is seen from another module, then the longest pairs."""
    present = window.present(labels)
    rows = [Row(settings.astronauts.get(k, k), f"{s:.0f} s", GREEN)
            for k, s in sorted(present.items()) if not k.startswith("unknown-")]
    unknown = [k for k in present if k.startswith("unknown-")]
    if unknown:
        rows.append(Row(f"Unknown: {len(unknown)} {'person' if len(unknown) == 1 else 'people'}", "", AMBER))
    rows += [Row(a, "", MUTED) for a in also]
    together: dict[str, float] = {}
    for (a, b), p in window.pairs.items():
        key = " + ".join(sorted((labels.get(a, f"unknown-{a}"), labels.get(b, f"unknown-{b}"))))
        together[key] = together.get(key, 0.0) + p.together_s
    rows += [Row(k, f"{s:.0f} s together", MUTED)
             for k, s in sorted(together.items(), key=lambda kv: -kv[1])[:MAX_PAIR_ROWS]]
    return rows or [Row("Nobody counted yet", "", MUTED)]


def run_ambiente(settings: Settings, sink: Sink, cameras: list[int], window_s: float = 60.0,
                 rotation: int | None = None, seconds: float = 0.0, overlap: bool = False,
                 trace: Path | None = None) -> None:
    gallery = gallery_of(settings)
    if not gallery.people:
        print("No enrolled faces: everyone shows as unknown-<n>. Run: wellbeing-vision enroll --astronaut ast-01")
    module_of = {i: settings.cameras.get(i, f"cam{i}") for i in cameras}
    if overlap:  # one shared space: every camera feeds the first camera's module
        module_of = dict.fromkeys(cameras, module_of[cameras[0]])
        print(f"--overlap: cameras {cameras} watch one space, counted as {module_of[cameras[0]]}; no transfers.")
    ids, start, t0 = itertools.count(1), datetime.now(UTC), time.monotonic()
    cams = [_Camera(settings, i, module_of[i], ids, rotation) for i in cameras]
    windows = {m: ModuleWindow(m, "vision:" + "+".join(f"cam{i}" for i in cameras if module_of[i] == m), start)
               for m in dict.fromkeys(module_of.values())}
    homes, labels, scores, transfers = Homes(), {}, {}, []
    window_t0, sent, n, t, errors = 0.0, 0, len(cams), 0.0, 0
    view = _Window("Ambient - wellbeing-vision")
    pool = ThreadPoolExecutor(max_workers=n)  # OpenCV and MediaPipe release the GIL: cameras run in parallel
    trace = unused_path(trace) if trace else None
    trace_file = trace.open("w", newline="", encoding="utf-8") if trace else None
    tracer = csv.writer(trace_file) if trace_file else None
    if tracer:
        tracer.writerow(TRACE_FIELDS)
    try:
        while not seconds or time.monotonic() - t0 < seconds:
            try:
                if not all(pool.map(lambda c: c.step(gallery, t0), cams)):
                    break
                t = time.monotonic() - t0
                sightings: dict[str, set[str]] = {}
                for c in cams:
                    for tr in c.seen:
                        if tr.astronaut:
                            sightings.setdefault(tr.astronaut, set()).add(c.module_id)
                            scores[tr.astronaut] = tr.score
                for e in [] if overlap else homes.update(sightings, t):
                    transfers = (transfers + [f"{datetime.now():%H:%M:%S} {e}"])[-3:]
                    print("Transfer", e)
                assign(cams, homes, sightings)
                for m, w in windows.items():
                    people = {}
                    for c in (c for c in cams if c.module_id == m):
                        for tr in c.seen:
                            labels[tr.id] = tr.label
                            counted = tr.elsewhere is None and tr.mature(t, settings.min_track_s)
                            if counted:
                                people[tr.id] = tr.pose
                            if tracer:
                                b = body(tr.pose)
                                tracer.writerow([f"{t:.3f}", c.module_id, tr.id, tr.label, int(counted),
                                                 int(tr.face_seen == tr.last_seen), int(tr.pose is not None),
                                                 f"{b.sw:.0f}" if b else "", f"{b.turn:.2f}" if b else "", tr.elsewhere or ""])
                    w.add(max(c.dt for c in cams if c.module_id == m), people)
                if t - window_t0 >= window_s:
                    sent += _flush(windows, sink, labels, scores, start + timedelta(seconds=t))
                    window_t0 = t

                # Preview: cameras stacked top to bottom, after the per-camera flip/turn and nothing else.
                tiles, boxes, lines, sections = [], [], [], []
                for k, c in enumerate(cams):
                    h, w = c.frame.shape[:2]
                    tiles.append(cv2.resize(c.frame, (640, round(640 * h / w))))
                    also = []
                    for tr in sorted(c.seen, key=lambda tr: tr.id):
                        name = settings.astronauts.get(tr.astronaut, tr.astronaut) if tr.astronaut else tr.label
                        if tr.elsewhere and tr.elsewhere != c.module_id:
                            name = f"{name} (seen from {tr.elsewhere})"
                            also.append(name)
                        young = not tr.mature(t, settings.min_track_s)
                        color = MUTED if young or tr.elsewhere else GREEN if tr.astronaut else AMBER
                        x0, y0, x1, y1 = tr.box  # face, or the body while the face is not seen
                        boxes.append((x0 / w, (k + y0 / h) / n, x1 / w, (k + y1 / h) / n, name, color))
                        if tr.pose is not None:  # each camera takes 1/n of the stacked preview's height
                            lines += [((a[0], (k + a[1]) / n), (b[0], (k + b[1]) / n)) for a, b in skeleton(tr.pose, w, h)]
                    if overlap and k > 0:
                        continue
                    where = "top" if k == 0 and n > 1 else "bottom" if n > 1 else "view"
                    fps = " / ".join(f"{x.fps:.0f}" for x in cams) if overlap else f"{c.fps:.0f}"
                    head = f"{c.module_id.upper()} · {'ALL CAMERAS' if overlap else f'CAM {c.index} ({where})'} · {fps} FPS"
                    sections.append((head, panel_rows(settings, windows[c.module_id], labels, also)))
                if transfers:
                    sections.append(("TRANSFERS", [Row(e, "", MUTED) for e in transfers]))
                left = max(0.0, window_s - (t - window_t0))
                status = f"WINDOW {int(left) // 60}:{int(left) % 60:02d} · {sent} sent"
                if not view.show(render(np.vstack(tiles), "AMBIENT", status, sections, FOOTER, boxes=boxes, lines=lines)):
                    break
            except Exception as e:  # one bad frame must never end the session: log it, keep going
                errors += 1
                if errors == 1 or errors % 100 == 0:
                    print(f"Frame error #{errors} (skipped): {type(e).__name__}: {e}")
    finally:
        t = time.monotonic() - t0
        if t - window_t0 >= MIN_PARTIAL_S:
            sent += _flush(windows, sink, labels, scores, start + timedelta(seconds=t))
        pool.shutdown()
        for c in cams:
            c.close()
        cv2.destroyAllWindows()
        if trace_file:
            trace_file.close()
        print(f"Sent {sent} records. FPS per camera: "
              + ", ".join(f"cam{c.index} {c.frames / t:.1f}" for c in cams if t > 0)
              + (f". Frames skipped by errors: {errors}" if errors else ""))
