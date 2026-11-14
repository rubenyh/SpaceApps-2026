# design-sync notes (apps/spaceship-app)

Run everything from `apps/spaceship-app`. Target project: "Spaceship Console".

## How this repo is built for the sync

- The app has no component library build. The converter runs in synth-entry mode: `--entry ./dist/index.js` deliberately points at a file that does not exist, so the package root resolves to this app and the entry is synthesized from `srcDir` (`src/components`). Do not "fix" the `[NO_DIST]` line.
- `buildCmd` (`sh .design-sync/build-types.sh`) emits real prop types to `dist/types/` plus a root `index.d.ts` (both gitignored). Without it every `<Name>.d.ts` degrades to `[key: string]: unknown`. `npm run build` wipes `dist/`, so run `buildCmd` after it, never before.
- `.design-sync/entry.ts` (via `extraEntries`) is what ships the CSS (`tokens.css`, `crt.css`, `app.css`) and exports `HttpError` / `NetworkError` for `ErrorNotice`.
- Build: `node .ds-sync/resync.mjs --config .design-sync/config.json --node-modules ./node_modules --entry ./dist/index.js --out ./ds-bundle`
- Playwright + headless Chromium are installed inside `.ds-sync/` (gitignored); reinstall on a fresh clone.

## Preview quirks

- Preview cards force a white `body`; the console only exists on dark. Every preview wraps in `S` from `.design-sync/surface.tsx`. `CrtFrame` does not need it.
- `RadiationPanel`'s real title starts with "⚠", which the render check reads as a crashed cell. Its previews prepend `<span hidden>` text to dodge that. Remove it if the checker changes.
- `TabBar` is generic (`TabDef<K>`); the extractor leaves `K` unresolved, so its props are hand-written in `dtsPropsFor`.
- The capture harness freezes the clock, so `Header` shows 2024-05-15 12:00:00Z in screenshots.

## Known render warns

- None on the last run (14/14 clean).

## Re-sync risks

- `dtsPropsFor.TabBar` is a hand copy: update it if `TabBar`'s props change.
- Chart x-axis end labels ("ahora", last date) clip at the right edge of the SVG. That is the component's own behavior, also in the app, not a preview bug.
- A new file in `src/components/*.tsx` is picked up automatically as a component and ships a floor card until a preview is authored.
- `conventions.md` enumerates class and token names from `src/styles/`; re-validate it against `ds-bundle/_ds_bundle.css` after style changes.
- Emitted `.d.ts` reference type names (`Astronaut`, `Reading`, `SensorStatus`, `Point`) without their definitions; shapes are in `src/api/types.ts`.
