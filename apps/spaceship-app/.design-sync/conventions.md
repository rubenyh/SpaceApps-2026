# Building with the Spaceship Console components

A green-phosphor CRT medical console. Monochrome green on near-black, monospace, Spanish UPPERCASE labels. No light theme exists.

## Setup

- Link `styles.css` once. It sets the dark page (`body` gets `--bg`, `--fg`, `--font`, the text glow). Without it everything renders unstyled black-on-white.
- No provider or theme wrapper is needed. Components are plain functions on `window.SpaceshipConsole`.
- Wrap a full screen in `CrtFrame` (scanlines + vignette, fills the viewport), then `<div className="app">` for page padding and vertical spacing:

```jsx
const { CrtFrame, Header, TabBar, Panel, StatusBadge, AgeLabel, SegmentedBar } = window.SpaceshipConsole;

<CrtFrame>
  <div className="app">
    <Header astronauts={crew} selectedId="ast-01" onSelect={setId} connection="online" />
    <TabBar tabs={[{ key: "vitales", label: "SIGNOS VITALES" }, { key: "orina", label: "ORINA" }]} active={tab} onChange={setTab} />
    <main className="main">
      <div className="screen">
        <div className="grid-2">
          <Panel title="PULSO" aside={<StatusBadge status="normal" />} className="statebox statebox--normal">
            <div className="vital__value">
              <span className="value-lg">72</span>
              <span className="unit">lpm</span>
              <AgeLabel seconds={4} />
            </div>
            <SegmentedBar value={72} normalMin={50} normalMax={100} label="PULSO" />
          </Panel>
        </div>
      </div>
    </main>
  </div>
</CrtFrame>
```

## Styling idiom: plain CSS classes + CSS variables

Style your own layout glue with the classes below and `var(--*)` tokens. Do not invent colors: the only non-green element allowed is `ColorSwatch`.

| Purpose | Names |
|---|---|
| Colors | `--bg`, `--bg-panel`, `--fg`, `--fg-bright`, `--fg-dim`, `--line`, `--overlay` |
| Type | `--font`, `--fs-small`, `--fs-base`, `--fs-title`, `--fs-value` |
| Effects | `--glow` (text-shadow), `--glow-svg` (filter), `--scanline-opacity` |
| Page layout | `app`, `main`, `screen`, `grid-2` (two equal columns), `toolbar`, `field` |
| Values | `value-lg`, `value-md`, `value-prefix`, `unit`, `vital__value` (baseline row: value, unit, age) |
| Text | `muted` (dim, small), `dimmed` (stale content at half opacity), `note`, `code`, `empty` |
| State frame | `statebox` + one of `statebox--normal`, `statebox--alert`, `statebox--stale`, `statebox--no_data`, `statebox--doubtful`, `statebox--exposure` |
| Markers | `badge` (use `StatusBadge` instead when you have a status), `tag` (e.g. `PROV.`) |
| Controls | `btn`, `btn--active`, `btn-group`; the active one shows its label in brackets, e.g. `[pH]` |
| Messages | `banner` (inverse-video, service-wide), `notice notice--error` (use `ErrorNotice` for request failures) |

`Panel` accepts `className`, so a state frame goes on the panel itself: `className="statebox statebox--alert"`.

## Rules the components encode

- State is never shown by color alone: every status has bracketed text (`[ OK ]`, `[!! ALERTA ]`, `[-- SIN DATOS ]`, `[~ VIEJO ]`, `[? SIN RANGO ]`). Use `StatusBadge` for it.
- Missing values are shown as `---`, never invented. Pass `null` and let the component render its empty state (`SegmentedBar` without a range draws no scale; charts take `emptyText`).
- `ErrorNotice` needs a real error object: `new window.SpaceshipConsole.HttpError(404, "detail")` or `new window.SpaceshipConsole.NetworkError("message")`.
- Chart `points` are `{ t: epochMs, v: number }`. `ScopeChart` is for a short live window (minutes), `TrendChart` for days or weeks.
- `RadiationPanel` is an indirect marker, never a dose: do not restyle it as OK or as a measured value.

## Where to look

- `styles.css` and its import `_ds_bundle.css`: every class and token above, verbatim from the app.
- `components/general/<Name>/<Name>.prompt.md` and `<Name>.d.ts`: per-component usage and props.
