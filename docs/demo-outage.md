# Outage demo: urgent incident while the Earth link is down

A second, shorter demo sends a crew-reviewed case report across the same outage: [Case report: ship to base](#case-report-ship-to-base-across-an-outage-and-a-restart).

Four beats in about 30 seconds:

1. A reading arrives.
2. The Earth link drops. Both consoles show it.
3. The crew sees the action and acknowledges it onboard.
4. The link returns. Ground shows the incident and the acknowledgment once, with event and receipt times.

The scenario uses its own astronaut, `scn-01` ("Scenario crew (scripted)"). The live simulator (`ast-*`) can keep running. The reading has source `simulated:scenario`. The urgent message is scripted, as if the crew had typed it.

## Setup

Start the stack as in [RUN-REPO.md](RUN-REPO.md) (`.\run.ps1`, or `docker compose up` plus both consoles). The demo controls (link pause/resume and the destructive incident reset) are off by default. Turn them on for the demo before starting the stack: `$env:DEMO_CONTROLS_ENABLED="true"` in PowerShell (or `DEMO_CONTROLS_ENABLED=true docker compose up -d` in a POSIX shell). Without it the control routes answer 403.

When you run the services natively, set `ONBOARD_DEMO_CONTROLS_ENABLED=true` for onboard-api and `GROUND_DEMO_CONTROLS_ENABLED=true` for ground-api. Both are off by default. While they are off, the control routes answer 403.

The script uses only the Python standard library. Run it from the repo root with any Python 3.12:

```sh
python services/onboard-api/scripts/incident_demo.py reset
python services/onboard-api/scripts/incident_demo.py run --step
```

`--onboard URL` and `--ground URL` change the default addresses (`http://127.0.0.1:8000` and `:8001`).

## Commands

| Step | Command | What it does |
|---|---|---|
| Reset | `incident_demo.py reset` | Restores the Earth link. Deletes the `scn-01` incidents and their events onboard (`DELETE /demo/incidents`) and on ground (ground `DELETE /demo/incidents`). Creates `scn-01` if it is missing. Idempotent. If a telemetry send is in flight, the onboard reset waits for it to end (at most the 10 s send timeout), so that batch cannot bring the deleted incident back to ground after the ground reset. |
| Run (presenter) | `incident_demo.py run --step` | Beat 1, then waits for Enter. Beat 2, then waits for the crew to press **Acknowledge**. Then waits for Enter and runs beat 4. |
| Run (crew paced) | `incident_demo.py run` | The same, without the Enter prompts. |
| Run (headless) | `incident_demo.py run --auto-ack` | The script acknowledges as `scn-01`. Used for the timing below. |
| Drop link | `incident_demo.py drop` (or `POST /telemetry/pause`) | Pauses the onboard telemetry publisher. |
| Restore link | `incident_demo.py restore` (or `POST /telemetry/resume`) | Resumes it. |

What reset keeps: readings, the simulator's data, and incidents of other astronauts.

### Why a pause and not `docker compose stop ground-api`

The pause is a controlled outage. The publisher sends nothing and counts no failures. Onboard work and the incident queue keep running. After resume, the queued updates go out at the next publisher step, within one telemetry interval (5 s).

Stopping ground-api also works, but each failed send doubles the retry delay, up to 60 s. The first send after `docker compose start ground-api` can then take a minute, which breaks the 30-second target. While ground-api is stopped, base-app shows "Ground not answering" instead of a late batch.

## What each console shows

Keep the spaceship console on crew member `scn-01 · Scenario crew (scripted)` and on the **Assistant** tab. Keep the ground console on the **Link** tab for beats 1 to 3, then switch to **Incidents** for beat 4.

| Beat | Spaceship console (onboard) | Ground console (base-app) |
|---|---|---|
| 1. Reading | **Vital signs** and **Records** tabs: SpO2 84 % with source `simulated:scenario`. Header: "Earth link: up". | Top bar: "Link up". |
| 2. Link drops | Header: "Earth link: down (simulated outage)". The Assistant tab shows "Open incident · Scenario crew (scripted)", "Next action", the "Simulated" tag on the SpO2 evidence (under "Full checklist, evidence and rules"), and "Ground delivery: queued, not delivered". "Mission guidance not loaded" also shows while the mission procedures are not loaded. | Top bar and Link tab: "Batch late" ("Batch late: 15 s without data") after 15 s without batches, "No link" after 60 s. "Time since the last batch" keeps counting. |
| 3. Acknowledge | Press **Acknowledge**. The card shows "Acknowledged onboard by <id> at <time> UTC". "Ground delivery: queued, not delivered" stays. | No change: nothing has arrived. |
| 4. Link returns | Header: "Earth link: up". The card shows "Delivered to ground <time> UTC". | Top bar: "Link up". The **Incidents** tab shows "Incident <id> immediate", "Astronaut scn-01", "Acknowledged onboard by <id> at <time>", and one row for each of "Incident began" and "Acknowledged onboard", with "Onboard time", "Received on ground" and "Delay" ("+N s after event" when the update waited onboard). |

Labels marked as scripted or simulated on screen: the crew member name "Scenario crew (scripted)" (both consoles), the reading source `simulated:scenario` (spaceship), the "Simulated" evidence tag (spaceship incident card), and "Earth link: down (simulated outage)" (spaceship header). The ground Incidents tab shows only the astronaut id `scn-01`, with no scripted tag.

Language: every screen of both consoles is in English, including the ground Crew, Astronaut and Alerts screens. Only file and route names (`Tripulacion.tsx`, `AsistenteScreen.tsx`) keep their Spanish names; nothing on screen does.

## Case report: ship to base across an outage and a restart

Every clinical assistant reply sends its case report to base automatically. The report waits in the onboard SQLite queue (`case_reports`) while ground is down, survives an onboard-api restart, and reaches ground once. Contract: [case-report](../contracts/case-report/README.md). The report is informational support; diagnosis and treatment decisions stay with qualified personnel.

1. Start ground-api (`services/ground-api`: `uv run fastapi dev --port 8001`) and onboard-api (`services/onboard-api`: `ONBOARD_DEMO_CONTROLS_ENABLED=true uv run fastapi dev`), then the device feed from the repo root: `python3 firmware/simulator.py` (needs Python 3.12; on Windows `python3` may be an older Python, use `python`).
2. Start both consoles ([RUN-REPO.md](RUN-REPO.md)). In the spaceship console, Assistant tab, crew member `ast-01`, type `im dizzy`. The reply is `Review required`; its report goes to base on its own and the tag turns **Received by base** within a few seconds.
3. Open **Review & send to base**. It shows the report text and "Readings in this report".
4. Take the link down: stop ground-api (Ctrl+C), or `POST /telemetry/pause` on onboard-api.
5. Type `im dizzy` again. The new reply's report tag is **Queued** (no button to press).
6. Restart onboard-api. The report stays **Queued** (`GET /case-reports/{id}`).
7. Bring the link back: start ground-api again, or `POST /telemetry/resume`. The tag changes to **Received by base** with ground's receipt time. After a stopped ground-api the first retry can wait up to 60 s (backoff). The pause is held in memory, so the onboard restart in step 6 already ends a paused outage.
8. In the ground console, **Reports** tab: exactly one row for the report. The **Incidents** tab lists case reports only for incidents (`immediate` replies); a `Review required` report has no incident.

Reset: `DELETE /demo/incidents?astronaut_id=<id>` on onboard-api and on ground-api (both demo-gated) also deletes that astronaut's case reports.

Verified 2026-11-15 at the API level, not in the consoles: native ground-api and onboard-api on ports 18001 and 18000 with temporary databases, Ollama not running, `python firmware/simulator.py --url http://127.0.0.1:18000 --no-history`. `POST /assistant/messages {"message":"im dizzy","astronaut_id":"ast-01"}` gave `review_required` and a `draft` report with 2 readings. With ground-api stopped, `POST /case-reports/{id}/send` gave `queued`; still `queued` after an onboard-api restart; `received` 13 s after ground-api started again; ground `GET /case-reports` listed the id once. The console steps (2, 3, 5, 8) and the pause variant were not run here (GUI).

## Results

### Headless script time (measured 2026-11-15)

Setup: ground-api and onboard-api run natively (`uv run uvicorn`) on ports 18001 and 18000, with temporary databases, telemetry interval 5 s, and no Ollama (the SOS path does not need it). Each run was `reset` followed by `run --auto-ack`. Times are as recorded by the independent QA rerun for each command.

| Run | Reset | Run, beat 1 to ground | Ground result |
|---|---|---|---|
| 1 | 0.2 s | 0.8 s | 1 incident (`scn-01`), updates `created` and `acknowledged` once each, 1 acknowledgment; onboard `ground_delivery` `delivered` |
| 2 | 0.3 s | 0.3 s | Same as run 1 |

Measured by the QA rerun on 2026-11-15 after resume started cutting the retry wait short. Before that change, runs took 1.2–4.3 s, depending on where the publisher was in its 5-second interval. In every run, `received_at` was at or after `occurred_at`.

### Docker Compose run (2026-11-15)

Disposable stack from this branch, its own project and volumes, next to an existing stack on 8000/8001. Ollama and demo-init were not started: the urgent path does not use them, and this also checks the "Ollama stopped" case.

```powershell
$env:DEMO_CONTROLS_ENABLED = "true"; $env:ONBOARD_API_PORT = "8010"; $env:GROUND_API_PORT = "8011"
docker compose -p sa26demo up --build -d onboard-api ground-api simulator
python services/onboard-api/scripts/incident_demo.py --onboard http://127.0.0.1:8010 --ground http://127.0.0.1:8011 reset
python services/onboard-api/scripts/incident_demo.py --onboard http://127.0.0.1:8010 --ground http://127.0.0.1:8011 run --auto-ack
docker compose -p sa26demo down -v   # removes the disposable data
```

| Check | Result |
|---|---|
| Both APIs healthy after `up --build` | yes, 19 s |
| `reset` + `run --auto-ack`, twice | same result both times: 1 `scn-01` incident on ground, `created` then `acknowledged`; script 0.6 s |
| Held outage: `drop`, SOS, 16 s wait, acknowledge as `ast-01`, `restore` | before restore: onboard `queued`, ground 404 and 16 s since the last batch. After restore: 1 incident, `created` (12:46:00.56) then `acknowledged` (12:46:16.86), both received 12:46:17.25; onboard `delivered` |
| Real outage: `docker compose stop ground-api`, SOS, acknowledge as `ast-02`, `start ground-api` | delivered 14 s after start (retry backoff); 1 incident, original times kept |
| Reset while a send is held in flight 4 s (native, delaying proxy) | before the fix: the old incident came back on ground, and the next rehearsal showed 2. After the fix: reset waits 4.1 s, ground keeps only the new incident |

### Pending human verification

| Item | Result |
|---|---|
| Four beats at human pace, from a clean reset (target: about 30 s) | pending |
| Second reset and run with the same result, on screen | pending |
| Screenshot or recording of each beat, both consoles | pending |
| First-use drill, new person: time to find the action | pending |
| First-use drill, new person: time to acknowledge | pending |
| Old chat-and-copy flow (`CaseReportBox` in `AsistenteScreen.tsx`): time to find and report, same person | pending |

Record the actual numbers, including the poor ones.
