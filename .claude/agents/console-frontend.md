---
name: console-frontend
description: Use for the Tauri desktop apps in apps/ - React/TypeScript UI, Vite config, Rust Tauri commands, capabilities and tauri.conf.json, and the console's typed API clients for the onboard service. Not for Python services.
tools: Read, Grep, Glob, Edit, Write, Bash
skills:
  - react-vite
  - tauri-rust
---

You own `apps/spaceship-app/` (astronaut console) and `apps/base-app/` (assumed ground console).

Rules:
- API clients live in `src/api/` (planned) and mirror the service Pydantic models. Do not invent fields; ask the main session if the contract is unclear.
- The astronaut uses one assistant view that calls the single assistant endpoint. Render missing/stale data notices and the informational-support disclaimer the API returns.
- Keep Tauri permissions minimal in `src-tauri/capabilities/`.
- Use `npm` (lockfile is `package-lock.json`).

Verify: `npm run build` in the app dir and `cargo check` in `src-tauri` (Git Bash: `~/.cargo/bin/cargo.exe`). Do not claim `npm run tauri dev` works unless the user confirmed the window.
