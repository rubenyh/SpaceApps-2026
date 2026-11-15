---
name: react-vite
description: Build the React + TypeScript + Vite UI of the Tauri apps, including the astronaut assistant view and typed clients for the onboard API. Use for anything under apps/*/src or vite.config.ts.
---

# React + Vite console

## Where
- `apps/spaceship-app/src/` - `main.tsx`, `App.tsx` (template). Astronaut console.
- `apps/base-app/src/` - same template. Assumed ground console.
- Versions (package.json): `react`/`react-dom` ^19.1.0, `vite` ^8.0.16, `@vitejs/plugin-react` ^6.0.2, `typescript` ~6.0.3, `@tauri-apps/api` ^2. Package manager: npm (`package-lock.json`).
- Vite dev server: spaceship-app 1420, base-app 1422, both `strictPort`, so both run at once.

## Do
- API clients (planned): `src/api/assistant.ts` and similar. Types mirror the service Pydantic models (`AssistantResponse` is in the `langgraph-workflows` skill). Base URL from `import.meta.env.VITE_ONBOARD_API_URL`, default `http://127.0.0.1:8000`.
- One assistant view in the astronaut console. Show `data_notices` and `disclaimer` next to the reply. When `needs_clarification` is true, show the question and keep the input focused.
- Show network failure as a visible state ("Onboard service unreachable"), not a blank screen.
- Use native elements and CSS before UI libraries. Ask before adding a dependency.

## Verify
```bash
cd apps/spaceship-app && npm run build    # tsc && vite build
```
No frontend tests yet. If added, use Vitest (`npm i -D vitest`) and commit `package-lock.json`.

Docs: https://vite.dev/guide/ , https://react.dev/reference/react , https://v2.tauri.app/start/frontend/vite/
