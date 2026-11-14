---
name: tauri-rust
description: Change the Rust side of the Tauri 2 apps - commands, plugins, capabilities and permissions, tauri.conf.json, and builds. Use for anything under apps/*/src-tauri.
---

# Tauri 2 (Rust)

## Where
- `apps/spaceship-app/src-tauri/` - crate `spaceship-app`, lib `spaceship_app_lib`, edition 2024. `src/lib.rs` holds the builder and the template `greet` command; `src/main.rs` calls `run()`.
- `apps/base-app/src-tauri/` - same template, lib `base_app_lib`. No `Cargo.lock` yet.
- Versions (Cargo.toml): `tauri = "2"`, `tauri-build = "2"`, `tauri-plugin-opener = "2"`, `serde`/`serde_json = "1"`. CLI `@tauri-apps/cli` ^2 (2.12.4 installed).
- Config: `tauri.conf.json` (dev URL `http://localhost:1420`, `frontendDist: ../dist`, `csp: null`). Permissions: `capabilities/default.json`.

## Do
- Prefer calling the onboard API from React with `fetch`. Add a Rust command only for what the webview cannot do (files, OS access).
- New command: `#[tauri::command]` function in `lib.rs` or a module, register it in `generate_handler![...]`, call it with `invoke` from `@tauri-apps/api/core`. Return `Result<T, String>` for errors.
- New plugin: `npm run tauri add <plugin>` from the app dir, then grant only the needed permissions in `capabilities/`.
- Before a release, replace `csp: null` with a CSP that allows the onboard API origin.
- `gen/` and `target/` are generated and gitignored. Commit `Cargo.lock`.

## Verify
```bash
cd apps/spaceship-app/src-tauri && cargo check    # Git Bash: ~/.cargo/bin/cargo.exe check
cd apps/spaceship-app && npm run tauri dev         # opens a window; the user confirms
```

Docs: https://v2.tauri.app/develop/calling-rust/ , https://v2.tauri.app/security/capabilities/ , https://v2.tauri.app/reference/config/
