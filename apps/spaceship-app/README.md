# spaceship-app (astronaut console)

Desktop console for the crew. Tauri 2 with React 19, Vite 8 and TypeScript 6. It talks only to [onboard-api](../../services/onboard-api/README.md) over HTTP (`fetch` in the webview); the Rust side opens the window and registers the `opener` plugin, with no custom commands.

Tabs: Status, Vital signs, Muscle, Urine, Assistant (chat, urgent incident panel), Records and Wellbeing (crew and personal views behind a demo PIN, daily check-in). The header shows the Earth link state, and a new urgent incident beeps on every tab. The UI text is English.

Data flow and polling intervals: [docs/ARCHITECTURE.md, flows 1 to 4](../../docs/ARCHITECTURE.md#end-to-end-flows). Design system: [DESIGN.md](DESIGN.md).

## Prerequisites

- Node.js with npm.
- Rust (`cargo` on `PATH`) and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for your OS. See [Troubleshooting](../../docs/TROUBLESHOOTING.md#desktop-consoles-tauri) if `cargo` is not found.
- onboard-api on `http://127.0.0.1:8000` ([root README](../../README.md#quickstart)).

## Commands

From `apps/spaceship-app`:

| Command | What |
|---|---|
| `npm install` | Install dependencies (once) |
| `npm run tauri dev` | Desktop window with hot reload. Vite on port 1420 (`strictPort`). |
| `npm run dev` | Vite only, in a browser at <http://localhost:1420> (no Tauri window) |
| `npm run build` | Type check (`tsc`) and production bundle. This is the project's lint step for TypeScript. |
| `node src/lib/<name>.check.ts` | Self-checks for the pure logic in `src/lib/` (`assistant`, `board`, `chartScale`, `estado`, `incident`, `wellbeing`). Each exits non-zero on a failure. |
| `cargo check` in `src-tauri/` | Check the Rust shell |
| `npm run tauri build` | Installer for the current OS (not used in the demo) |

## Configuration

`VITE_ONBOARD_API_URL` (default `http://127.0.0.1:8000`) and `VITE_WELLBEING_PINS` are read at build time. Details: [CONFIGURATION.md](../../docs/CONFIGURATION.md#desktop-consoles-build-time-vite_).

```powershell
$env:VITE_ONBOARD_API_URL = "http://127.0.0.1:8010"; npm run tauri dev
```

## Code map

| Path | What |
|---|---|
| `src/App.tsx` | Shell: crew selection, tabs, shell-level polls |
| `src/api/` | Typed clients. `types.ts` mirrors `services/onboard-api/src/onboard_api/schemas/` by hand: change both together. |
| `src/screens/` | One component per tab; `screens/wellbeing/` for the wellbeing views |
| `src/lib/` | Pure logic with `.check.ts` self-checks |
| `src-tauri/` | Rust shell, `tauri.conf.json`, capabilities |
