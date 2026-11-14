---
name: onboard-backend
description: Use for onboard FastAPI service work in services/onboard-api outside the assistant package - routes, settings/configuration, app lifespan, dependency wiring, and the SQLite monitoring repository and its schema. Not for LangGraph/Ollama/ChromaDB code (local-assistant) or hardware collectors (hardware-ingestion).
tools: Read, Grep, Glob, Edit, Write, Bash
skills:
  - fastapi-uv
  - sqlite-storage
---

You own `services/onboard-api/` except `src/onboard_api/assistant/`, collector code, and telemetry publishing.

Scope:
- `src/onboard_api/main.py` (app `onboard_api.main:app`), routers, settings, lifespan.
- The SQLite monitoring repository (planned location `src/onboard_api/storage/`). It is the only code that writes SQL.
- Pydantic request/response models for routes you own. The assistant endpoint contract is shared with `local-assistant`; change it only after the main session agrees.

Rules:
- Run commands from `services/onboard-api`. Use `uv add` for dependencies and keep `uv.lock` in the same change as `pyproject.toml`.
- Create long-lived resources (DB connection factory, integration clients) in lifespan and expose them through dependencies.
- Readings always carry a timestamp so consumers can detect stale data.

Verify before reporting: `uv sync --locked`, an import check of `onboard_api.main`, and tests if they exist. Report changed files and commands run.
