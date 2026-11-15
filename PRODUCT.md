# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Desktop app built with Tauri 2 + React (web technology in a native window). Window 1280×800, minimum 1024×700. Not designed for mobile.

## Users

Primary: an astronaut on the spacecraft checking their own health readings and asking the onboard assistant, with no doctor present and no guaranteed ground link. The console has a crew selector, so any crew member can view any crew member's readings, and a report can be filed on behalf of a crewmate.

Secondary (planned): the ground base, which will see the same data through telemetry (`apps/base-app`, `services/ground-api`; not built yet).

## Product Purpose

Gives each astronaut a clear, honest view of their body during the mission (vital signs, muscle, urine) fed by onboard sensors, plus a local assistant for symptoms and health questions. Success: the astronaut knows at a glance what is normal, what needs attention and what is missing or old, and knows when to call the crew medical officer.

## Positioning

Readings come from the spacecraft's own sensors: a wearable pulse oximeter per astronaut (heart rate, SpO₂), a shared urine analyser (pH, salinity, color, temperature) and a muscle scanner. It sits at a medical station onboard, and the same data is meant to reach the ground base. A generic health dashboard has neither the device feed nor the ship-to-ground loop.

## Operating Context

- Onboard, offline-first: the console talks to the onboard service (`services/onboard-api`) on the local network. The assistant runs locally (Ollama, ChromaDB); no cloud calls.
- Readings arrive continuously from devices. Until the hardware exists, `firmware/simulator.py` stands in for it and behaves like the real device.
- Tabs: Status, Vital signs, Muscle, Urine, Assistant, Records.

## Capabilities and Constraints

- Built: live readings per sensor with status (alert, old data, no data, no range, normal), trends, raw records, and the medical triage assistant (16 reviewed protocols, urgency, evidence, sources).
- Planned: a journal (logbook) to follow mental health over time. Scope not confirmed yet; nothing for it is built, routed or designed.
- Planned: medical station hardware and ship-to-ground telemetry so the base can see the data.
- Visible UI text is in English. The onboard assistant still answers in Spanish (open decision).
- Never invent values, units or ranges. If something is undefined, missing or old, the UI says so. Ranges marked PROV. are provisional demo values, not clinically validated.
- Radiation is an indirect urine marker: shown only as "possible exposure, needs confirmation", never as a dose.
- The assistant gives supporting information only; diagnosis and treatment stay with qualified personnel.

## Evidence on Hand

- Visual identity: shared with the ground console (`apps/base-app`). Source of truth: `apps/spaceship-app/src/styles/tokens.css` (Barlow Condensed, steel/flap surfaces, red alert, amber old data, grey for no data; normal is plain text, never green; 2 px radius; sidebar navigation plus a top bar).
- Design reference: `docs/diseno/` (static mockups of the six tabs and states, `HANDOFF.md`). Use the mockups for structure and state logic only; their navy palette and system font are superseded. HANDOFF.md still says the UI is in Spanish; English now applies.
- Medical agent plan: `docs/plan-agente-medico-space-apps.md`.
- All crew data is synthetic (one simulated astronaut, `ast-01`). No real crew data, testimonials or validation studies exist; do not fabricate them.

## Product Principles

1. Honest over reassuring: missing or old data is never shown as fine.
2. Glanceable state: an astronaut sees what needs attention without reading every number.
3. Support, not diagnosis: no clinician is on board, so give cited first-aid steps the astronaut can act on, point to the mission emergency procedure, and say what guidance is missing.
4. Works without the ground: everything essential runs onboard.

## Accessibility & Inclusion

State is never conveyed by color alone: every state has its own icon shape and text label. Only alerts change the card border (red). No text below 14 px. Touch targets at least 44 px.
