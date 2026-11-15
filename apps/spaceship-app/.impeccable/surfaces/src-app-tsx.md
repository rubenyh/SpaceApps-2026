---
version: 2
slug: "src-app-tsx"
primary_target: "src/App.tsx"
related_targets: []
---

# Biomedical console (apps/spaceship-app)

Scope: the onboard astronaut console, seven tabs in the sidebar (Status, Vital signs, Muscle, Urine, Assistant, Records, Wellbeing). Mode: Operate. English UI. Restyled to the ground console's identity (`apps/base-app`) with a dashboard layout; DESIGN.md beside this app is the visual authority.
Audience: an astronaut at the medical station, no doctor present, no guaranteed ground link. Tasks: see at a glance what is normal, in alert, old or missing; read the trend; ask the assistant; check raw records; review wellbeing.
Data: onboard-api (`/readings`, status, incidents, `POST /assistant/messages`, wellbeing). Never invent values or ranges; stale, missing and no-range are states. PROV. marks provisional ranges.

## Direction contract

THESIS: A calm operations dashboard on a split-flap station board: a monochrome screen when all is well, where only trouble takes colour and every state is legible in grayscale. Refuses decorative charts, colour-only state and a green "normal".

OWN-WORLD: The ground console's board: steel #15171a page and sidebar, flap #0b0b0d cards, housing #1c1e22 insets, frame #2a2d31 1px lines, steel-mid #5b5e63 control borders, label #a7aaaf, letter #f2f2f2. Red #c8452f for out of bounds and amber #ffb000 for old data, each with a drawn icon and text; grey outline for no data / no range; normal is plain letter white. Barlow Condensed 500/600/700 for all text with tabular figures; uppercase tracked labels. One flat card pattern, 2px corners, no shadows. Split-flap plates on key reading values only.

STORY: Glance at Status → see the red attention banner and which organ is flagged → open the tab from the sidebar → read the flap value, range track and trend → ask the assistant or call the crew medical officer.

FIRST VIEWPORT: Sidebar (brand, seven navigation items with red/amber state flags), 56px top bar (screen title, crew selector, connection chips, UTC clock), Status: attention banner on alert, reading cards with flap values around the body map, radiation note. No header band, no footer legend.

FORM: Identity replacement of the previous navy instrument panel by the base-app identity, with sidebar + top bar dashboard structure. Signature: split-flap value plates, instrument charts (round ticks, 6% zone with dashed edges and margin values, 2px white trace red only outside the zone, breaks at gaps) and the range track.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
