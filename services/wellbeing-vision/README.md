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
| `uv run wellbeing-vision bitacora --astronaut ast-01 [--camera 0] [--seconds 60] [--dry-run]` | Daily video log: 3 s neutral, then fatigue and tension with a live preview. Sends one summary. |
| `uv run pytest` | Unit tests (no camera needed). |

`--dry-run` prints the JSON instead of posting it (add `--out file.jsonl` to also save it).
Without `--dry-run`, summaries are POSTed to `WELLBEING_VISION_API_URL`; if the API is down they go to
`outbox/pending.jsonl` and are retried on the next send. Payloads the API rejects (4xx) are parked in
`outbox/rejected.jsonl`.

## Settings (env vars)

| Variable | Default |
|---|---|
| `WELLBEING_VISION_API_URL` | `http://127.0.0.1:8000` |
| `WELLBEING_VISION_CAMERAS` | `{"0":"modulo-a","1":"modulo-b"}` |
| `WELLBEING_VISION_ASTRONAUTS` | `{"ast-01":"ast-01", ... "ast-04":"ast-04"}` |
| `WELLBEING_VISION_MODELS_DIR` / `_DATA_DIR` | `models` / `data` |

## Thresholds

All thresholds (eye closed, yawn, nod) are PROVISIONAL, relative to the astronaut's own neutral of the day,
and not clinically validated. Every payload carries `"provisional": true`.
