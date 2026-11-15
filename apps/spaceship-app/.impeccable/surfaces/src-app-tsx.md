---
version: 1
slug: "src-app-tsx"
primary_target: "src/App.tsx"
related_targets: []
---

# Biomedical console (apps/spaceship-app)

Scope: the onboard astronaut console, six tabs (Status, Vital signs, Muscle, Urine, Assistant, Records). Mode: Operate. English UI. Code-led refinement of the incumbent identity; DESIGN.md beside this app is the visual authority.
Audience: an astronaut at the medical station, no doctor present, no guaranteed ground link. Tasks: see at a glance what is normal, in alert, old or missing; read the trend; ask the assistant; check raw records.
Data: onboard-api (`/readings`, status, `POST /assistant/messages`). Never invent values or ranges; stale, missing and no-range are states. PROV. marks provisional ranges.
Evidence: screenshots of the refined build at 1280 and 1024 for every tab (session scratchpad `after2/`).

## Direction contract

THESIS: A spacecraft medical instrument panel: each reading is a gauge whose state is legible in grayscale. Refuses the white card-grid wellness dashboard and decorative charts.

OWN-WORLD: NASA blue band #0B3D91 with a 3px red rule #C8301A over navy surfaces (#0A1020 / #111A2E / #17223A), 1px hairlines, instrument blue #6EA2FF for interaction only. State tokens: alert coral/fill, normal green, old-data amber dashed, no-data gray dotted, no-range sky double; always icon + text + border. IBM Plex Sans with Plex Mono for units, ages, axes, clock. Radii 4/3/2. No shadows.

STORY: Glance at Status → see the attention banner and which organ is flagged → open the tab → read value, range track and trend → ask the assistant or call the crew medical officer.

FIRST VIEWPORT: Header band (brand, crew selector, UTC clock, connection), tab bar with state flags, Status: attention banner on alert, four reading cards around the body map, radiation note, footer state legend.

FORM: Code-led refinement of the existing console, seed: none (pinned) "Code-led refinement: the identity is kept". Signature: instrument charts (niceScale ticks, 5% zone tint with edge values in the margin, near-white 1.5px trace red only outside the zone, breaks at gaps, mono last-value label) and the bracketed range track.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
