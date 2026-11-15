# Troubleshooting

Known setup problems and how to fix them. Variables are explained in [CONFIGURATION.md](CONFIGURATION.md); commands in [RUN-REPO.md](RUN-REPO.md).

## Desktop consoles (Tauri)

**`npm run tauri dev` fails with "failed to run 'cargo metadata'" or "cargo: command not found".** The Tauri CLI needs `cargo` on `PATH`. rustup installs it in `~/.cargo/bin`, but an open terminal (and Git Bash on Windows) may not have that directory on `PATH`.

```sh
export PATH="$HOME/.cargo/bin:$PATH"     # Git Bash, macOS, Linux
cargo --version
```

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"   # PowerShell, this session only
cargo --version
```

If rustup is not installed, install it from <https://rustup.rs> and follow the Tauri prerequisites for your OS: <https://v2.tauri.app/start/prerequisites/> (on Windows: Microsoft C++ Build Tools and WebView2).

**The first `npm run tauri dev` takes minutes.** Cargo compiles the Tauri crate once. Later starts reuse `src-tauri/target`.

**"Port 1420 is already in use" (or 1422).** Both Vite configs use `strictPort`. Another console or Vite process holds the port, often a Vite left over from an earlier run or another worktree. `.\run.ps1` checks both ports first, prints the PID and command line, and skips that console. Find it yourself with `Get-NetTCPConnection -LocalPort 1420 -State Listen` and stop it with `Stop-Process -Id <pid>`. spaceship-app uses 1420 and base-app uses 1422, so the two consoles can run at the same time.

**The console shows "ONBOARD SERVICE UNAVAILABLE" (or base-app shows "No connection to the ground service").** The API is not running, or the console points at another URL. Check `curl http://127.0.0.1:8000/` (or `:8001`). If you moved the port, start the console with `VITE_ONBOARD_API_URL` or `VITE_GROUND_API_URL`. If you serve the console from another origin, add it to `ONBOARD_CORS_ORIGINS` or `GROUND_CORS_ORIGINS`.

**`.\run.ps1` fails with "running scripts is disabled on this system".** Run it once with `powershell -ExecutionPolicy Bypass -File .\run.ps1`. The same policy blocks `npm.ps1`; run `npm.cmd` instead of `npm` in that shell.

## Ollama and the assistant

**Replies contain "The local model (Ollama) did not respond: showing the preserved card or guide text."** The chat model is missing or Ollama is not running. Alarm and card decisions still work. Fix:

```sh
ollama list                     # qwen2.5:3b and bge-m3 must appear
ollama pull qwen2.5:3b
ollama pull bge-m3
curl http://127.0.0.1:11434/api/tags
```

In Docker Compose, the models live in the `ollama` volume, not on the host. Check with `docker compose logs demo-init` and rerun `docker compose up demo-init`.

**Replies contain "The embedding model (Ollama) did not respond: the local guides were not searched."** `bge-m3` is missing or Ollama is down. Pull the model as above.

**Replies contain "The local guides (ChromaDB) could not be searched."** The guide index is empty or missing at `ONBOARD_CHROMA_PATH`. Build it ([RAG-AND-EVALUATION.md](RAG-AND-EVALUATION.md#build-or-rebuild-the-index)). In Compose, wait until `docker compose ps -a` shows `demo-init` as `Exited (0)`. The API sees a first ingest without a restart. After a rebuild of an existing index, restart onboard-api.

**An educational question gets "I did not find a local source that supports an answer to this question ...".** No English guide chunk was close enough (`ONBOARD_RETRIEVAL_MAX_DISTANCE`). This is the intended abstention, not an error. Run the retrieval evaluation to check the index.

**The first assistant reply after a start takes a long time, or the interpreter times out.** A cold load of `qwen2.5:3b` on CPU can take longer than `ONBOARD_OLLAMA_INTERPRET_TIMEOUT_SECONDS` (15 s). The turn then continues with the rule interpreter only. Compose keeps the models loaded (`OLLAMA_KEEP_ALIVE=-1`). Natively, load the model once before the demo: `curl http://127.0.0.1:11434/api/generate -d '{"model": "qwen2.5:3b"}'`.

**The ingest exits with "Manifest embedding_model ... != ONBOARD_OLLAMA_EMBED_MODEL ...; aborting."** The embedding model in `corpus/manifest.json` and the setting differ. Use the manifest value, or change both and re-ingest.

**A native Ollama and the Compose stack at the same time.** They do not conflict: the Compose `ollama` service does not publish port 11434. They keep separate model stores, so pull the models into each one you use.

## Python services

**`UnicodeEncodeError` from the `fastapi` CLI, pytest or the ingest on Windows.** Set `PYTHONUTF8=1` (`$env:PYTHONUTF8 = "1"` in PowerShell).

**`curl -d '...'` with accented text fails with "There was an error parsing the body" in Git Bash.** Send the body from stdin with `--data-binary @-` and a heredoc, as in the [onboard-api examples](../services/onboard-api/README.md#examples). In PowerShell, use `Invoke-RestMethod` with `-ContentType "application/json; charset=utf-8"`.

**`uv sync` fails because files in `.venv` are locked.** OneDrive or an antivirus holds them. Pause OneDrive sync, or keep the clone outside OneDrive, and retry.

**Startup fails with `RuntimeError` from `apply_migrations`.** The database is newer than the code, or a migration failed. Use a fresh `ONBOARD_DB_PATH`, or update the checkout. Migration rules: [`db/data-dictionary.md`](../db/data-dictionary.md).

**Port 8000 or 8001 is already in use.** A native `uv run fastapi dev` and the Compose stack both want these ports. Stop one, or move Compose with `ONBOARD_API_PORT` and `GROUND_API_PORT` ([CONFIGURATION.md](CONFIGURATION.md#docker-compose-substitutions)).

## Docker Compose

**`demo-init` exits with a non-zero code.** Read `docker compose logs demo-init` (lines start with `[prepare-demo]`). Common causes: Ollama not healthy after 300 s, no network for the model pull or the MedlinePlus download, not enough disk space (the first run downloads about 7 GB). Rerun with `docker compose up demo-init`.

**`docker compose up` fails at once.** Docker Desktop is not running.

**The console header shows "Earth link: ground not answering".** ground-api is down or `ONBOARD_GROUND_API_URL` is wrong. onboard-api keeps working and sends the backlog when ground-api answers again.

**`POST /telemetry/pause` returns 403.** Demo controls are off. Start the stack with `DEMO_CONTROLS_ENABLED=true` ([demo-outage.md](demo-outage.md)).

**`GET /medical-eval/approved/bundle` returns 409 in Compose** (found by reading the code and the Dockerfile, not by a run). The ground-api image contains only `services/ground-api`, so the approved component files are not on disk. Run ground-api natively from `services/ground-api` for the knowledge release flow, or set `GROUND_BUNDLE_ROOT` to a directory with the repo files.
