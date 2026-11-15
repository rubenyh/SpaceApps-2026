# Building with the Spaceship Console components

A biomedical console for astronauts. It shares one visual identity with the ground console (`apps/base-app`): steel/flap dark surfaces, Barlow Condensed (bundled with `@fontsource`), uppercase labels, English text, 2 px radius. Token source of truth: `src/styles/tokens.css`. `docs/diseno/` mockups are for structure and state logic only; their navy palette is superseded. No light theme exists.

## Setup

- Link `styles.css` once. It sets the dark page (`body` gets `--color-bg`, `--color-text`, `--font-sans`). Without it everything renders unstyled black-on-white.
- No provider or theme wrapper is needed. Components are plain functions on `window.SpaceshipConsole`.
- A full window is `<div className="app">`: an `<aside className="sidebar">` (brand + vertical `TabBar`), `Header` (renders the `topbar`) and `<main className="main">`. There is no footer:

```jsx
const { Header, TabBar, ReadingCard, RangeTrack } = window.SpaceshipConsole;

<div className="app">
  <aside className="sidebar">
    <h1 className="sidebar__brand">Biomedical console</h1>
    <TabBar tabs={[{ key: "estado", label: "Status" }, { key: "orina", label: "Urine" }]} active={tab} onChange={setTab} flags={{ orina: "stale" }} />
  </aside>
  <Header title="Status" astronauts={crew} selectedId="ast-01" onSelect={setId} connection="online" />
  <main className="main">
    <div className="screen">
      <ReadingCard title="Pulse" organ="Heart" status="normal" value="72" unit="bpm" ageSeconds={4} quality="good" explanation="Within the normal range">
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
| Surfaces | `--color-bg` (steel), `--color-surface` (flap), `--color-surface-2` (housing), `--color-border` / `--color-rule` (frame), `--color-control` (steel-mid) |
| Text | `--color-text`, `--color-text-muted`, `--color-text-faint`, `--color-accent` |
| States | `--state-alert`, `--state-alert-fill`, `--state-normal`, `--state-stale`, `--state-nodata`, `--state-norange`, `--range-zone`; borders `--border-alert`, `--border-normal`, `--border-nodata`, `--border-dubious` |
| Type | `--font-sans`, `--font-mono`, `--text-xs` (14 px, the minimum) to `--text-2xl`, `--data` (flap value, 26 px, 36 px from 1200 px), `--weight-regular` / `--weight-medium` / `--weight-bold` |
| Space and shape | `--space-1` to `--space-10`, `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-pill` (all 2 px), `--target-min` (44 px) |
| Page layout | `app`, `sidebar`, `sidebar__brand`, `tabbar`, `topbar`, `main`, `screen`, `screen--fill`, `panel` / `panel__head`, `toolbar`, `field`; sizes `--sidebar-w`, `--header-h`, `--page-pad`, `--gap` |
| Messages | `banner` + `banner--alert`, `banner--error`, `banner--stale`, `banner--empty`; `infobox`; `empty` (centred empty state) |
| Controls | `btn`, `btn--ghost`, `btn--on-alert`; use `SegmentedControl` for exclusive choices |
| Small pieces | `caption` (muted 14 px), `prov` (the PROV. tag), `stats` / `stat`, `flap` / `flap--plate` / `flap--red` (split-flap value, use the `Flap` component), `sr-only` |

## Rules the components encode

- State is never shown by color alone: every status has its own icon shape and text (`StatusPill`, `StateIcon`). Only red (alert), amber (old data) and grey (no data, no range, doubtful) are state colours; normal is plain text, never green. Only an alert changes the card border. The five states are `alert`, `normal`, `stale`, `no_data`, `no_range`, plus `doubtful` for a sample-validity range out of bounds.
- `doubtful` (urine temperature) is never an alert. `RadiationPanel` is an indirect marker, never a dose: do not restyle it as normal or as a measured value.
- Missing values are shown as `---`, never invented. Ranges, the PROV. flag and the range source come from the service config; pass `null` and let the component render its empty state.
- `ServiceBanner` needs a real error object: `new window.SpaceshipConsole.HttpError(404, "detail")` or `new window.SpaceshipConsole.NetworkError("message")`.
- Chart `points` are `{ t: epochMs, v: number }`. `LineChart` covers both the short live window and day/week trends (`showPoints` for sparse series). Times are UTC.
- All visible text is English, at 14 px or more. Touch targets are at least 44 px.

## Where to look

- `styles.css` and its import `_ds_bundle.css`: every class and token above, verbatim from the app.
- `components/general/<Name>/<Name>.prompt.md` and `<Name>.d.ts`: per-component usage and props.
