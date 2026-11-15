# base-app (ground console)

Desktop console for the ground team. Tauri 2 with React 19, Vite 8 and TypeScript 6. It talks only to [ground-api](../../services/ground-api/README.md) over HTTP; the Rust side has no custom commands. It never calls onboard-api: everything it shows arrived on ground through telemetry.

Screens: Crew (status board), Astronaut (charts per sensor), Alerts, Incidents (read-only), Eval (review medical-eval candidates, record a clinician or simulated decision, flag missing scenarios) and Link (link state and a ledger of changes). The UI text is English; some file names are Spanish (`Tripulacion.tsx`, `Alertas.tsx`, `Enlace.tsx`).

Data flow and polling intervals: [docs/ARCHITECTURE.md, flow 6](../../docs/ARCHITECTURE.md#6-telemetry-and-ground-console) and [flow 7](../../docs/ARCHITECTURE.md#7-knowledge-release-evaluation-review-activation).

## Prerequisites

- Node.js with npm.
- Rust (`cargo` on `PATH`) and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/). See [Troubleshooting](../../docs/TROUBLESHOOTING.md#desktop-consoles-tauri).
- ground-api on `http://127.0.0.1:8001`, receiving telemetry from onboard-api ([root README](../../README.md#quickstart)).

## Commands

From `apps/base-app`:

| Command | What |
|---|---|
| `npm install` | Install dependencies (once) |
| `npm run tauri dev` | Desktop window with hot reload. Vite on port 1421 (`strictPort`), so it can run next to spaceship-app (1420). |
| `npm run dev` | Vite only, in a browser at <http://localhost:1421> |
| `npm run build` | Type check (`tsc`) and production bundle |
| `node src/lib/<name>.check.ts` | Self-checks for `board`, `incidents` and `medicalEval` |
| `cargo check` in `src-tauri/` | Check the Rust shell |

## Configuration

`VITE_GROUND_API_URL` (default `http://127.0.0.1:8001`), read at build time. Details: [CONFIGURATION.md](../../docs/CONFIGURATION.md#desktop-consoles-build-time-vite_).

## Code map

| Path | What |
|---|---|
| `src/App.tsx` | Shell: tabs, link, crew and alert polls, offline banner |
| `src/api/` | Typed ground-api client; `types.ts` mirrors `services/ground-api/src/ground_api/schemas.py` by hand |
| `src/screens/` | One component per screen |
| `src/lib/` | Pure logic with `.check.ts` self-checks |
| `src-tauri/` | Rust shell, `tauri.conf.json`, capabilities |
