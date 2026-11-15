# wellbeing-vision

Camera analysis for the crew wellbeing module. Runs as its own process next to `onboard-api`.
Only derived metrics leave the process: no frames are stored or sent.

## Setup (Windows, PowerShell)

```powershell
cd services/wellbeing-vision
uv sync --locked
uv run wellbeing-vision models   # downloads ~45 MB into models/ (not committed)
```

The repo lives in OneDrive: if `.venv` files get locked during `uv sync`, pause OneDrive sync and retry.

## Commands

| Command | What |
|---|---|
| `uv run wellbeing-vision models` | Download MediaPipe and OpenCV Zoo models. |
| `uv run wellbeing-vision bitacora --astronaut ast-01 [--camera 0] [--seconds 60] [--no-mirror] [--trace t.csv] [--dry-run]` | Daily video log: 3 s neutral, then fatigue and tension with a live preview. Sends one summary. Keys: `f` fullscreen, `q`/Esc end. |
| `uv run wellbeing-vision enroll --astronaut ast-01 [--camera 0] [--samples 10]` | Enroll a face: 10 templates while turning the head a little. Replaces the previous enrollment. Not mirrored: only the daily log mirrors (self-view, `--no-mirror` to turn it off). |
| `uv run wellbeing-vision identify [--camera 0] [--rotate 180] [--seconds 0]` | Multi-person preview: one box per tracked face with its name or `unknown-<n>`, and the linked pose. Sends nothing. |
| `uv run wellbeing-vision ambiente [--cameras 0 1] [--window 60] [--rotate 180] [--seconds 0] [--dry-run]` | Ambient mode: each camera is a module; every window sends co-presence and one motion session per person. Preview with both cameras stacked. |
| `uv run pytest` | Unit tests (no camera needed). |

`--dry-run` prints the JSON instead of posting it (add `--out file.jsonl` to also save it).
Without `--dry-run`, summaries are POSTed to `WELLBEING_VISION_API_URL`; if the API is down they go to
`outbox/pending.jsonl` and are retried on the next send. Payloads the API rejects (4xx) are parked in
`outbox/rejected.jsonl`.

## Cameras

Every camera command (`bitacora`, `enroll`, `identify`, `ambiente`) opens cameras the same way: it asks for
1280x720 and, with `auto`, tries DSHOW first and falls back to MSMF if DSHOW does not open or gives no frame in
2 s (USB phone-webcam apps often only work with MSMF). It prints the backend and the resolution each camera
really delivers, and warns when it is not 1280x720 (faces look smaller). A camera that opens with no
backend stops the command with an error naming the index and what was tried; it never ends silently.

## Daily video log (bitácora) capture

The log is a **controlled-distance capture: frontal, ~50 cm from the camera, good light, same time each day**.
- The camera is opened at 1280x720 (MJPG); the resolution actually delivered is printed at start.
- A square crop around the face (seeded by YuNet, then following the landmarks) is what the Face Landmarker sees,
  so the face is found even when small in the frame.
- Frames where the face is narrower than `WELLBEING_VISION_MIN_FACE_PX` (default 160 px cheek to cheek, about
  80 cm on a 720p webcam) show "Move closer to the camera" and are not usable: they add nothing to blinks, PERCLOS or
  tension and lower `valid_frame_ratio` (below 0.8 the session is `suspect`, below 0.5 `bad`).
- The log is spoken to the camera. Neutral calibration needs 3 s in a row with the face close, still, relaxed
  and looking at the camera. A blink, a head move over 5°, talking or looking away restarts it, and the hint
  on screen says why. The neutral is then rejected if the eyes are not plausibly open (eyeBlink median over
  0.3).
- Long-term anchor: each accepted neutral is appended (numbers only) to `data/neutrals/<astronaut>.jsonl`.
  The anchor is the median of the last 7 neutrals (from 3 on). If today's neutral EAR is more than 15 % off
  the anchor, calibration is asked once more. If it is off again, the eyes are measured against the anchor.
  The anchor moves slowly, so it follows a gradual change (a puffy face in microgravity) but not one bad day.
- Eye closure (blinks, PERCLOS) uses the eyeBlink blendshape over `max(0.4, neutral + 0.25)`, not EAR. EAR of
  open eyes doubles when the face moves back, so it needs the day's neutral. `eye_openness_vs_neutral` is
  still the EAR ratio.
- Looking down (reading) lowers the lids and the brows. Frames looking down for over 0.5 s (eyeLookDown
  0.25 over neutral, or the head 15° down without the eyes going up) show "Look at the camera" and are not
  usable, unless the eyes are deeply shut (eyeBlink 0.6 or more, which still counts as closed).
- A nod is a drop of the head past 15° that comes back under 10° within 0.3-2 s. Staying down is a posture.
- Lip press is measured only while not talking: two jaw openings within 1 s, plus 0.5 s after, count as
  talking (a single opening, like a swallow, does not). With less than 10 s of quiet time,
  `lip_press_delta` and `lip_press_peak_1s` are `null`.
- `--trace t.csv` writes per-frame derived numbers (face px, EAR and its ratio, eyeBlink, jaw/brow/lip deltas,
  talking flag, head pitch and yaw, eyeLookDown/Up, looking-down flag) to tune thresholds. No images. It
  never overwrites: if `t.csv` exists it writes `t-2.csv`, `t-3.csv`... and prints the path.

## Identity

- YuNet finds the faces; SFace turns each one into a 128-number template, aligned by the eyes first, so an
  upside-down face matches an upright enrollment. Templates live in `data/faces/<astronaut>.npz` (local,
  gitignored). They are biometric data: never sent, never committed; delete the file to remove a person.
- A face is an astronaut when the cosine match is at least 0.363 (the threshold published with SFace) and
  0.08 ahead of the runner-up (PROVISIONAL). Each tracked face averages its last 10 templates, needs 3 before
  it gets a name, and one astronaut can only be one face at a time; the rest show as `unknown-<track>`.
- Orientation: YuNet needs roughly upright faces, so the frame is tried at 0, 180, 90 and 270 degrees,
  starting with the last one that worked. `--rotate N` fixes it (demo: `--rotate 180`). One orientation per
  frame: an upright and an upside-down person are not seen at the same time.
- IoU tracker (overlap 0.3, 15 frames of grace). MediaPipe Pose (up to 4 people) is linked to the face box
  that holds the pose's nose; a pose narrower than the face is dropped as a misfire.
- The daily log checks its face every 10 frames against the gallery. If it confirms the claimed astronaut,
  the payload says `identity.method: "face"` with the median score, and up to 3 frames scoring 0.5 or more
  are added to the gallery (at most 20 such templates, oldest dropped). Otherwise it stays `manual` and the
  reason is printed.

## Ambient mode

- One process, one camera per module (`WELLBEING_VISION_CAMERAS`, default cam 0 = `modulo-a`, cam 1 =
  `modulo-b`), processed in parallel threads. Each camera has its own tracker, orientation and pose model.
- Identity is resolved across cameras: one astronaut is one face at a time. Seeing them in the other module
  is a transfer (preview and console). Unidentified people are `unknown-<track>`, unique across cameras.
- Every window (60 s) and module: `POST /wellbeing/co-presence` with occupants (1 s or more), pairs
  (seconds together, mean distance in shoulder widths, facing ratio) and quality (camera coverage). Empty
  windows are not sent. A window cut short by quitting is sent if it lasted 10 s or more.
- Per person with 10 s or more of pose: `POST /wellbeing/vision-sessions` with `session_type: "ambiente"`,
  `neutral_ok: false` (no facial neutral) and `motion`: torso `speed` (shoulder widths/s),
  `stationary_ratio` (under 0.1 sw/s), `fidget_index` (wrist speed relative to the torso, sw/s) and
  `torso_angle_dev` (degrees of the head against the shoulder line, from its median in the window). All
  relative to the body, so the numbers do not change with the camera or the astronaut upside down.
  Steps over 5 sw/s are tracking jumps and are skipped. PROVISIONAL.
- Presence comes from detected faces: someone with their back to the camera is not counted.
- Preview: cameras stacked top to bottom, shown as delivered (no mirror, no rotation); boxes, skeletons,
  per-module occupants and pairs, transfers, FPS per camera and the window countdown.

## Settings (env vars)

| Variable | Default |
|---|---|
| `WELLBEING_VISION_API_URL` | `http://127.0.0.1:8000` |
| `WELLBEING_VISION_CAMERAS` | `{"0":"modulo-a","1":"modulo-b"}` |
| `WELLBEING_VISION_ASTRONAUTS` | `{"ast-01":"ast-01", ... "ast-04":"ast-04"}` |
| `WELLBEING_VISION_MIN_FACE_PX` | `160` (PROVISIONAL) |
| `WELLBEING_VISION_CAMERA_BACKEND` | `auto` (DSHOW, then MSMF); `dshow` or `msmf` to force one. Also `--backend` on every camera command. |
| `WELLBEING_VISION_MODELS_DIR` / `_DATA_DIR` | `models` / `data` |

## Thresholds

All thresholds (eye closed, yawn, nod, calibration, anchor, talking, looking down) are PROVISIONAL, tuned on one person's
traces, and not clinically validated. Every payload carries `"provisional": true`.
