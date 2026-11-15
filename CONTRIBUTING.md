# Contributing

How changes get into `main`. Setup: [README](README.md#quickstart). Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Checks before a pull request

There is no CI and no separate linter or formatter config. The checks below are the gate; run the ones for the parts you changed and list the results in the PR.

| Part | Working directory | Command |
|---|---|---|
| onboard-api | `services/onboard-api` | `uv sync --locked`, then `uv run pytest -q` |
| ground-api | `services/ground-api` | `uv sync --locked`, then `uv run pytest -q` |
| wellbeing-vision | `services/wellbeing-vision` | `uv sync --locked`, then `uv run pytest -q` (no camera needed) |
| Device simulator | `firmware` | `python test_simulator.py` |
| spaceship-app | `apps/spaceship-app` | `npm run build` (type check and bundle), `node src/lib/<name>.check.ts` for each changed `src/lib` module |
| base-app | `apps/base-app` | `npm run build`, `node src/lib/<name>.check.ts` |
| Tauri shells | `apps/*/src-tauri` | `cargo check` |
| watch-app (macOS) | `apps/watch-app` | `swiftc WatchApp/Api.swift Checks/main.swift -o /tmp/watch-checks && /tmp/watch-checks` |
| Assistant behavior | `services/onboard-api` | The medical case suite ([RAG-AND-EVALUATION.md](docs/RAG-AND-EVALUATION.md#medical-case-suite)) when you change cards, rules, prompts, the corpus or models |

On Windows, set `PYTHONUTF8=1` before the Python commands.

## Conventions

- **Branches.** Fetch first (`git fetch origin`), then branch from `origin/main` as `agent/<owner>/<task>` without tracking `main`: `git switch --no-track -c agent/<owner>/<task> origin/main`. One writer per branch. Parallel sessions on one machine use separate worktrees.
- **Commits and PR titles** follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `<type>(<scope>): <description>`, for example `fix(telemetry): validate capture timestamps` or `docs(architecture): describe onboard workflows`.
- **Pull requests.** Push early and open a draft PR. Keep the description current: scope, checks run, remaining work. Before asking for a merge, fetch again and review `git diff origin/main...HEAD`.
- **Merging.** Every change to `main` goes through a PR approved by the repo owner. Merge with a merge commit (`gh pr merge <n> --merge`), never squash or rebase. Do not force-push shared branches.
- **Dependencies.** Add Python packages with `uv add <pkg>` (or `uv add --dev`) and commit `uv.lock` with `pyproject.toml`.
- **Contracts.** Agree on a shared interface (Pydantic model, route, JSON schema) before changing both sides. The TypeScript types in `apps/*/src/api/types.ts` are hand-written mirrors of the Pydantic schemas; change both together. The telemetry contract lives in [`contracts/telemetry/`](contracts/telemetry/README.md).
- **Database.** Add a numbered SQL file to `db/migrations/onboard/` (never edit an applied one) and update [`db/data-dictionary.md`](db/data-dictionary.md).
- **Medical content.** Answers are informational support only. Missing or stale data is stated, never filled in. Evaluation cases stay `draft` until a named clinician reviews them ([`eval/medical/README.md`](eval/medical/README.md)).
- **Local only.** Services make no cloud LLM or vector database calls.
- **Docs.** When a change affects setup commands, configuration, architecture or a contract, update the one canonical page: [README](README.md) (quickstart), [RUN-REPO](docs/RUN-REPO.md) (all run options), [CONFIGURATION](docs/CONFIGURATION.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [RAG-AND-EVALUATION](docs/RAG-AND-EVALUATION.md).

Claude Code sessions also follow [`CLAUDE.md`](CLAUDE.md), which lists the subagents and skills in `.claude/`.
