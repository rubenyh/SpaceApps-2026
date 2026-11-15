import cv2
import numpy as np
import pytest

from wellbeing_vision.identity import AUTO_MAX, Face, Gallery, best_match, rotate, unrotate, verify
from wellbeing_vision.tracker import IoUTracker, Track, iou, observations, resolve


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=128).astype(np.float32)
    return v / np.linalg.norm(v)


def _face(x0, y0, x1=None, y1=None) -> Face:
    x1, y1 = x1 or x0 + 100, y1 or y0 + 100
    row = np.zeros(15, np.float32)
    row[14] = 0.95  # YuNet confidence
    return Face(np.array([x0, y0, x1, y1], float), row, 0)


@pytest.mark.parametrize("deg", [0, 90, 180, 270])
def test_unrotate_maps_points_back_to_the_frame(deg):
    frame = np.zeros((720, 1280), np.uint8)
    frame[100, 300] = 255  # x=300, y=100
    ys, xs = np.nonzero(rotate(frame, deg))
    assert unrotate(np.array([[xs[0], ys[0]]], float), deg, 1280, 720).tolist() == [[300, 100]]


def test_gallery_round_trip_and_auto_cap(tmp_path):
    a, b = _unit(1), _unit(2)
    g = Gallery(tmp_path)
    g.enroll("ast-01", [a, a])
    g.enroll("ast-02", [b])
    loaded = Gallery(tmp_path).load(["ast-01", "ast-02", "ast-03"])
    assert set(loaded.people) == {"ast-01", "ast-02"}
    assert loaded.scores(a)["ast-01"] == pytest.approx(1.0)
    for i in range(AUTO_MAX + 5):
        loaded.add_auto("ast-01", [_unit(100 + i)])
    reloaded = Gallery(tmp_path).load(["ast-01"]).people["ast-01"]
    assert len(reloaded["auto"]) == AUTO_MAX and len(reloaded["enrolled"]) == 2


def test_best_match_needs_threshold_and_margin():
    assert best_match({"ast-01": 0.6, "ast-02": 0.2}) == ("ast-01", 0.6)
    assert best_match({"ast-01": 0.6, "ast-02": 0.55})[0] is None  # too close to call
    assert best_match({"ast-01": 0.3})[0] is None  # under the SFace threshold
    assert best_match({}) == (None, 0.0)


def test_verify_confirms_and_picks_strong_templates():
    t = _unit(3)
    good = [({"ast-01": s, "ast-02": 0.1}, t) for s in (0.45, 0.6, 0.7, 0.55, 0.52)]
    identity, add, _ = verify(good, "ast-01")
    assert identity.method == "face" and identity.match_score == 0.55
    assert len(add) == 3  # only frames over AUTO_ENROLL, best first
    # Someone else's face: not sent at all (None), not even as manual.
    wrong, add, msg = verify([({"ast-01": 0.1, "ast-02": 0.87}, t)] * 3, "ast-01")
    assert wrong is None and add == [] and "ast-02" in msg
    assert verify([({"ast-02": 0.87}, t)], "ast-01")[0] is None  # ast-01 not enrolled, but it is ast-02
    # Nobody matches confidently, or nobody is enrolled: manual.
    assert verify([({"ast-01": 0.2, "ast-02": 0.25}, t)] * 3, "ast-01")[0].method == "manual"
    assert verify([], "ast-01")[0].method == "manual"


def test_tracker_keeps_ids_while_faces_move_and_drops_old_tracks():
    tr = IoUTracker()
    for i in range(10):  # two people drifting 5 px per frame
        tr.update([_face(100 + 5 * i, 100), _face(700 - 5 * i, 120)], i)
    assert [t.id for t in tr.tracks] == [1, 2]
    tr.update([_face(1000, 500)], 10)  # a third person; the others are not seen
    assert [t.id for t in tr.tracks] == [1, 2, 3]
    tr.update([], 30)
    assert tr.tracks == []
    assert iou(np.array([0, 0, 10, 10]), np.array([5, 0, 15, 10])) == pytest.approx(1 / 3)


def test_resolve_gives_each_astronaut_to_one_track():
    a, b, c = Track(1, _face(0, 0), 0), Track(2, _face(300, 0), 0), Track(3, _face(600, 0), 0)
    for i in range(3):
        a.vote({"ast-01": 0.7, "ast-02": 0.1}, i)
        b.vote({"ast-01": 0.5, "ast-02": 0.1}, i)  # also looks like ast-01, but less
        c.vote({"ast-01": 0.1, "ast-02": 0.2}, i)  # nobody enrolled
    resolve([a, b, c])
    assert (a.label, b.label, c.label) == ("ast-01", "unknown-2", "unknown-3")


def test_identity_needs_several_votes():
    t = Track(1, _face(0, 0), 1, face_seen=1)
    t.vote({"ast-01": 0.9}, 0)
    resolve([t])
    assert t.astronaut is None and t.needs_template(1)  # face seen in frame 1: wants more votes


def _pose(cx, top, sw=200.0, face_visible=True):
    """A seated person: nose at (cx, top), shoulders below. Turned away: the nose is not visible."""
    p = np.zeros((33, 3))
    p[0] = (cx, top, 1.0 if face_visible else 0.1)
    p[11], p[12] = (cx - sw / 2, top + 120, 1.0), (cx + sw / 2, top + 120, 1.0)
    p[23], p[24] = (cx - sw / 3, top + 400, 1.0), (cx + sw / 3, top + 400, 1.0)
    return p


def test_observations_pair_faces_with_bodies():
    a, b = _face(100, 100), _face(600, 100)  # faces 100 px wide
    pose_b, back, on_face = _pose(650, 150), _pose(1000, 150, face_visible=False), _pose(150, 150, sw=40)
    obs = observations([a, b], [on_face, pose_b, back])
    assert obs[0] == (a, None)  # the narrow misfire on a's face is neither a's body nor a second person
    assert obs[1][0] is b and obs[1][1] is pose_b
    assert obs[2][0] is None and obs[2][1] is back  # someone with their back to the camera
    assert len(obs) == 3


def test_a_person_who_turns_away_keeps_the_track_and_the_name():
    tr = IoUTracker()
    face = lambda x: _face(x - 50, 100)  # noqa: E731
    for i in range(5):  # looking at the camera: face and body, identified
        (t,) = tr.update([face(300 + i)], i, [_pose(300 + i, 150)])
        t.vote({"ast-01": 0.8}, i)
    resolve([t])
    assert t.label == "ast-01"
    for i in range(5, 60):  # turned away for 55 frames: no face, body drifting
        seen = tr.update([], i, [_pose(305 + i, 150, face_visible=False)])
        assert [s.id for s in seen] == [t.id] and not t.needs_template(i)
        resolve(seen)
    assert t.label == "ast-01" and t.face_seen == 4 and (t.box == t.body).all()
    (back,) = tr.update([face(365)], 60, [_pose(365, 150)])  # face again
    assert back is t and t.needs_template(60) and (t.box == t.face.box).all()
    assert len(tr.tracks) == 1


def test_render_draws_boxes_without_touching_the_input():
    from wellbeing_vision.overlay import GREEN, render

    frame = np.zeros((720, 1280, 3), np.uint8)
    out = render(frame, "IDENTITY", "1 in view", [], "footer", boxes=[(0.1, 0.2, 0.3, 0.5, "ast-01", GREEN)],
                 lines=[((0.2, 0.5), (0.2, 0.9))])
    assert frame.max() == 0 and out[int(0.2 * 720), int(0.15 * 1280)].any()
    assert cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)[int(0.7 * 720), int(0.2 * 1280)] > 0


def test_identify_shows_the_frame_as_delivered_with_boxes_in_place(monkeypatch):
    import wellbeing_vision.identify as ident
    from wellbeing_vision.config import Settings
    from wellbeing_vision.overlay import AMBER

    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[:100, :100] = (255, 255, 255)  # marker in the top-left corner of the camera image
    face = _face(600, 300, 700, 420)

    class FakeID:
        deg = 0

        def detect(self, img, orientations):
            assert orientations == (180,)
            self.deg = 180
            return [face]

    shown = []
    monkeypatch.setattr(ident, "face_id", lambda s: FakeID())
    monkeypatch.setattr(ident, "gallery_of", lambda s: Gallery(None))
    monkeypatch.setattr(ident, "_pose_landmarker", lambda s: type("P", (), {
        "detect_for_video": lambda self, img, ms: type("R", (), {"pose_landmarks": []})(), "close": lambda self: None})())
    monkeypatch.setattr(ident, "open_configured", lambda i, *a: type("C", (), {
        "read": lambda self: (True, frame), "release": lambda self: None})())
    for name in ("namedWindow", "destroyAllWindows", "setWindowProperty"):
        monkeypatch.setattr(ident.cv2, name, lambda *a, **k: None)
    monkeypatch.setattr(ident.cv2, "imshow", lambda n, c: shown.append(c))
    monkeypatch.setattr(ident.cv2, "waitKey", lambda *a: ord("q"))
    monkeypatch.setattr(ident.cv2, "getWindowProperty", lambda *a: 1)
    ident.run_identify(Settings(), 0, rotation=180)
    out = shown[0]  # 1280x720 video at scale 1, panel to the right
    assert out[50, 50].tolist() == [255, 255, 255] and out[670, 1230].tolist() == [0, 0, 0]  # not rotated/mirrored
    assert out[420, 650].tolist() == list(AMBER[::-1])  # bottom edge of the box, where the face is


def test_low_frame_rate_jumps_keep_one_track():
    # 4 FPS, person moving 60 px between frames (face 100 px): IoU drops but the predicted centre matches.
    tr = IoUTracker()
    for k in range(20):
        tr.update([_face(100 + 60 * k, 100)], k * 0.25)
    assert [t.id for t in tr.tracks] == [1]


def test_unknown_coming_back_in_the_same_place_keeps_its_track():
    tr = IoUTracker()
    for k in range(10):
        tr.update([_face(300, 100)], k * 0.1)
    tr.update([], 4.0)  # gone 3 s: the track ends
    assert tr.tracks == []
    (back,) = tr.update([_face(305, 100)], 6.0)
    assert back.id == 1 and back.mature(6.0)  # same unknown, its age kept
    (other,) = tr.update([_face(1000, 500)], 6.1)
    assert other.id == 2 and not other.mature(6.1)


def test_phantom_faces_are_dropped():
    tiny, unsure = _face(0, 0, 20, 20), _face(300, 0)
    unsure.row[14] = 0.75  # no body and not confident enough
    assert observations([tiny, unsure], []) == []
    assert observations([unsure], [_pose(350, 50)])[0][0] is unsure  # with a body it is a person


def test_a_pose_with_shoulders_but_no_box_does_not_make_a_boxless_track():
    # Shoulders exactly at the visibility bar and nothing else: body() accepts it, but it has no box.
    p = np.zeros((33, 3))
    p[11], p[12] = (100, 200, 0.5), (300, 200, 0.5)
    tr = IoUTracker()
    for k in range(3):
        assert all(t.box is not None for t in tr.update([], k * 0.1, [p]))
