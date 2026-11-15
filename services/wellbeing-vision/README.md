# wellbeing-vision

Camera analysis for the crew wellbeing module (optional). Runs as its own process next to `onboard-api` and posts to `POST /wellbeing/vision-sessions` ([contract](../../docs/wellbeing-contract.md)). Only the daily video log (`bitacora`) is implemented; identity, co-presence and demo modes are planned.
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
| `uv run pytest` | Unit tests (no camera needed). |

`--dry-run` prints the JSON instead of posting it (add `--out file.jsonl` to also save it).
Without `--dry-run`, summaries are POSTed to `WELLBEING_VISION_API_URL`; if the API is down they go to
`outbox/pending.jsonl` and are retried on the next send. Payloads the API rejects (4xx) are parked in
`outbox/rejected.jsonl`.

## Daily video log (bitácora) capture

The log is a **controlled-distance capture: frontal, ~50 cm from the camera, good light, same time each day**.
- The camera is opened at 1280x720 (MJPG); the resolution actually delivered is printed at start.
- A square crop around the face (seeded by YuNet, then following the landmarks) is what the Face Landmarker sees,
  so the face is found even when small in the frame.
- Frames where the face is narrower than `WELLBEING_VISION_MIN_FACE_PX` (default 160 px cheek to cheek, about
  80 cm on a 720p webcam) show "Acércate a la cámara" and are not usable: they add nothing to blinks, PERCLOS or
  tension and lower `valid_frame_ratio` (below 0.8 the session is `suspect`, below 0.5 `bad`).
- Neutral calibration needs 3 s in a row with the face close, still and relaxed. A blink, a head move over 5°
  or talking restarts it, and the hint on screen says why. The neutral is then rejected if the eyes are not
  plausibly open (eyeBlink median over 0.25).
- Long-term anchor: each accepted neutral is appended (numbers only) to `data/neutrals/<astronaut>.jsonl`.
  The anchor is the median of the last 7 neutrals (from 3 on). If today's neutral EAR is more than 15 % off
  the anchor, calibration is asked once more. If it is off again, the eyes are measured against the anchor.
  The anchor moves slowly, so it follows a gradual change (a puffy face in microgravity) but not one bad day.
- Eye closure (blinks, PERCLOS) uses the eyeBlink blendshape over `max(0.4, neutral + 0.25)`, not EAR. EAR of
  open eyes doubles when the face moves back, so it needs the day's neutral. `eye_openness_vs_neutral` is
  still the EAR ratio.
- Lip press is measured only while not talking (jaw travel under 0.15 in 1 s, plus 0.5 s after). With less
  than 10 s of quiet time, `lip_press_delta` and `lip_press_peak_1s` are `null`.
- `--trace t.csv` writes per-frame derived numbers (face px, EAR and its ratio, eyeBlink, jaw/brow/lip deltas,
  talking flag) to tune thresholds. No images.

## Settings

Environment variables `WELLBEING_VISION_*` (API URL, cameras, astronauts, minimum face size, directories): [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md#wellbeing-vision-wellbeing_vision_).

## Thresholds

All thresholds (eye closed, yawn, nod, calibration, anchor, talking) are PROVISIONAL, tuned on one person's
traces, and not clinically validated. Every payload carries `"provisional": true`.
