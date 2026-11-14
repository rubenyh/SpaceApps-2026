# Building with the Spaceship Console components

A biomedical console for astronauts. Dark navy surfaces, system sans-serif, Spanish sentence-case text. Visual reference: `docs/diseno/` (HANDOFF.md and the static mockups). No light theme exists.

## Setup

- Link `styles.css` once. It sets the dark page (`body` gets `--color-bg`, `--color-text`, `--font-sans`). Without it everything renders unstyled black-on-white.
- No provider or theme wrapper is needed. Components are plain functions on `window.SpaceshipConsole`.
- A full window is `<div className="app">` with `Header`, `TabBar`, `<main className="main">` and `<footer className="footer">`:

```jsx
const { Header, TabBar, ReadingCard, RangeTrack } = window.SpaceshipConsole;

<div className="app">
  <Header astronauts={crew} selectedId="ast-01" onSelect={setId} connection="online" />
  <TabBar tabs={[{ key: "estado", label: "Estado" }, { key: "orina", label: "Orina" }]} active={tab} onChange={setTab} flags={{ orina: "stale" }} />
  <main className="main">
    <div className="screen">
      <ReadingCard title="Pulso" organ="Corazón" status="normal" value="72" unit="lpm" ageSeconds={4} quality="good" explanation="Dentro de lo normal">
        <RangeTrack value={72} scale={[40, 160]} config={pulseConfig} status="normal" />
      </ReadingCard>
    </div>
  </main>
</div>
```

## Styling idiom: plain CSS classes + CSS variables

Style your own layout glue with the classes below and `var(--*)` tokens from `tokens.css`. Do not invent colors.

| Purpose | Names |
|---|---|
| Surfaces | `--color-bg`, `--color-surface`, `--color-surface-2`, `--color-border`, `--color-brand`, `--color-brand-rule` |
| Text | `--color-text`, `--color-text-muted`, `--color-text-faint`, `--color-accent` |
| States | `--state-alert`, `--state-alert-fill`, `--state-normal`, `--state-stale`, `--state-nodata`, `--state-norange`, and the matching `--border-*` |
| Type | `--font-sans`, `--text-xs` (14 px, the minimum) to `--text-2xl`, `--value-sm` / `--value-md` / `--value-lg` |
| Space and shape | `--space-1` to `--space-10`, `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-pill`, `--target-min` (44 px) |
| Page layout | `app`, `main`, `footer`, `screen`, `screen--fill`, `toolbar`, `field` |
| Messages | `banner` + `banner--alert`, `banner--error`, `banner--stale`, `banner--empty`; `infobox`; `empty` (centred empty state) |
| Controls | `btn`, `btn--ghost`, `btn--on-alert`; use `SegmentedControl` for exclusive choices |
| Small pieces | `caption` (muted 14 px), `prov` (the PROV. tag), `stats` / `stat`, `sr-only` |

## Rules the components encode

- State is never shown by color alone: every status has its own icon shape, text and border style (`StatusPill`, `StateIcon`). The five states are `alert`, `normal`, `stale`, `no_data`, `no_range`, plus `doubtful` for a sample-validity range out of bounds.
- `doubtful` (urine temperature) is never an alert. `RadiationPanel` is an indirect marker, never a dose: do not restyle it as normal or as a measured value.
- Missing values are shown as `---`, never invented. Ranges, the PROV. flag and the range source come from the service config; pass `null` and let the component render its empty state.
- `ServiceBanner` needs a real error object: `new window.SpaceshipConsole.HttpError(404, "detail")` or `new window.SpaceshipConsole.NetworkError("message")`.
- Chart `points` are `{ t: epochMs, v: number }`. `LineChart` covers both the short live window and day/week trends (`showPoints` for sparse series). Times are UTC.
- All visible text is Spanish, at 14 px or more. Touch targets are at least 44 px.

## Where to look

- `styles.css` and its import `_ds_bundle.css`: every class and token above, verbatim from the app.
- `components/general/<Name>/<Name>.prompt.md` and `<Name>.d.ts`: per-component usage and props.
