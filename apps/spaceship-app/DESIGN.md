---
name: Biomedical console
description: Onboard astronaut health console: navy instrument panel, NASA band and rule, state that never relies on color alone.
colors:
  bg: "#0A1020"
  surface: "#111A2E"
  surface-2: "#17223A"
  border: "#2A3854"
  rule: "#1F2B44"
  brand: "#0B3D91"
  brand-rule: "#C8301A"
  on-signal: "#FFFFFF"
  text: "#F1F4F9"
  text-muted: "#A7B2C6"
  text-faint: "#8592AA"
  accent: "#6EA2FF"
  state-alert: "#FF6A4D"
  state-alert-fill: "#C8301A"
  state-alert-tint: "rgba(255, 106, 77, 0.08)"
  state-normal: "#3DD68C"
  state-stale: "#F5B841"
  state-nodata: "#8592AA"
  state-norange: "#8AB4FF"
typography:
  display-lg:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "72px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  display:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "56px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  headline-lg:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 600
  headline:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 600
  title:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 600
  body-lg:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    letterSpacing: "0.08em"
  caption:
    fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  mono-unit:
    fontFamily: "IBM Plex Mono, ui-monospace, Menlo, Consolas, monospace"
    fontSize: "18px"
    fontWeight: 400
  mono:
    fontFamily: "IBM Plex Mono, ui-monospace, Menlo, Consolas, monospace"
    fontSize: "14px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  sm: "2px"
  md: "3px"
  lg: "4px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
components:
  header:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.on-signal}"
    height: "60px"
    padding: "0 24px"
  tab:
    textColor: "{colors.text-muted}"
    typography: "{typography.body-lg}"
    height: "52px"
    padding: "0 20px"
  tab-active:
    textColor: "{colors.text}"
    height: "52px"
    padding: "0 20px"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    rounded: "{rounded.md}"
    height: "44px"
    padding: "0 18px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    height: "44px"
    padding: "0 18px"
  button-on-alert:
    backgroundColor: "{colors.on-signal}"
    textColor: "{colors.state-alert-fill}"
    rounded: "{rounded.md}"
    height: "44px"
    padding: "0 18px"
  pill-alert:
    backgroundColor: "{colors.state-alert-fill}"
    textColor: "{colors.on-signal}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "4px 11px 4px 9px"
  pill-normal:
    backgroundColor: "transparent"
    textColor: "{colors.state-normal}"
    rounded: "{rounded.sm}"
    padding: "4px 11px 4px 9px"
  pill-stale:
    backgroundColor: "transparent"
    textColor: "{colors.state-stale}"
    rounded: "{rounded.sm}"
    padding: "4px 11px 4px 9px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
  card-alert:
    backgroundColor: "{colors.state-alert-tint}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
  banner-alert:
    backgroundColor: "{colors.state-alert-fill}"
    textColor: "{colors.on-signal}"
    rounded: "{rounded.lg}"
    padding: "12px 18px 12px 20px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "16px 18px"
  panel-heading:
    textColor: "{colors.text-muted}"
    typography: "{typography.label}"
    height: "52px"
  input-chat:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.md}"
    height: "46px"
    padding: "0 14px"
  segmented-button:
    textColor: "{colors.text-muted}"
    typography: "{typography.caption}"
    height: "42px"
    padding: "0 14px"
  segmented-button-active:
    textColor: "{colors.text}"
    height: "42px"
    padding: "0 14px"
---

# Design System: Biomedical console

## Overview

**Creative North Star: "The Flight Instrument Panel"**

The console reads like a medical instrument bolted into a spacecraft rack: a navy panel under a NASA-blue band with a red rule, readings set large in tabular figures, and every number standing on a hairline scale. It is a dark, dense, glanceable surface for a 1280×800 window (minimum 1024×700). Nothing floats; depth comes from three navy steps and 1px rules, and the only loud color on a calm screen is the state of a reading.

State is the system's grammar. Each reading state owns a color, a drawn icon, a text label and a border pattern, and all three channels travel together, so an astronaut can tell "alert" from "old data" from "no range" in grayscale. Charts behave like instruments, not infographics: round ticks, a faint normal zone with its edge values printed in the margin, a near-white trace that turns red only where it leaves the zone, and a mono readout of the last value.

The identity is fixed: the blue band (#0B3D91) and red rule (#C8301A) carry the mission brand; IBM Plex Sans and Plex Mono carry the voice; corners stay tight (4/3/2px).

**Key Characteristics:**
- NASA-blue header band with a 3px red rule; navy surfaces below.
- State shown by icon + text + border pattern, never by color alone.
- Large tabular reading values in Plex Sans; units, ages, axes and clocks in Plex Mono.
- Tight radii (4px containers, 3px controls, 2px tags) and 1px hairlines.
- Flat: no drop shadows; tonal steps and rules give structure.
- Instrument-style line charts and range tracks.

## Colors

A deep navy field with one brand band, one interactive blue, and five reserved state colors.

### Primary
- **Mission Blue** (brand): the 60px header band only. Text on it is white; its controls use white-mixed outlines (white 45% into the band).
- **Mission Red Rule** (brand-rule): the 3px rule under the header band and the orbit stroke of the brand mark. Same hex as the alert fill: red belongs to the mission mark and to alerts, nowhere else.

### Secondary
- **Instrument Blue** (accent): the one interactive color. Active tab underline, primary buttons, focus ring (2px outline, 2px offset), links, the clarification frame in the assistant, text selection (38% mix), caret.

### Neutral
- **Deep Space Navy** (bg): window background and inset fields (chat input, selects in the assistant).
- **Panel Navy** (surface): cards, panels, tab bar, footer, table.
- **Raised Navy** (surface-2): table header, chat bubbles, triage blocks, skeletons, body-map figure.
- **Frame Line** (border): 1px borders of cards, panels, inputs, segmented controls; range rail.
- **Hairline** (rule): grid lines, panel-head dividers, table row rules, stat underlines.
- **Panel White** (text): primary text, chart trace, last-value label.
- **Muted Label** (text-muted): secondary text, units, panel headings, captions.
- **Faint Label** (text-faint): axis ticks, range-track end values, timestamps, disabled tabs.
- **Signal White** (on-signal): text on the blue band and on the alert fill.

### State
- **Alert Coral** (state-alert): alert text, 2px solid alert border, chart trace outside the zone, alert markers. **Alert Fill** (state-alert-fill) carries white text on alert pills, the attention banner and immediate triage. **Alert Wash** (state-alert-tint) is the background of an alert card.
- **Normal Green** (state-normal): normal pills (1.5px outline), the chart zone tint (5%) and edges (60%), the range-track bracket (10% fill).
- **Old-Data Amber** (state-stale): dashed borders and text for stale readings.
- **No-Data Gray** (state-nodata): dotted borders; the same value as Faint Label, by design: missing data looks absent.
- **No-Range Sky** (state-norange): 3px double borders and the diamond marker.

### Named Rules
**The Three-Channel State Rule.** Every reading state is shown by icon + text + border pattern: alert 2px solid coral, old data 2px dashed amber, no data 2px dotted gray, no range 3px double sky, doubtful sample 2px solid muted. Color is the fourth channel, never the only one.

**The Red Means Out Rule.** Red appears only for the mission rule and for readings or services that are out of bounds. A healthy screen has no red below the header.

## Typography

**Display Font:** IBM Plex Sans (with Helvetica Neue, Arial, system-ui)
**Body Font:** IBM Plex Sans
**Label/Mono Font:** IBM Plex Mono (with ui-monospace, Menlo, Consolas)

**Character:** Plex Sans is the engineered, slightly technical voice of the panel; Plex Mono marks anything that is measured or timed. Bundled weights: Sans 400/500/600, Mono 400/500; 600 is the heaviest weight.

### Hierarchy
- **Display** (500, 56px, line-height 1, -0.02em, tabular): the current value in a reading card. 72px on Vital signs; 44px in small cards.
- **Headline** (600, 22px): attention-banner title. 28px for empty-state titles.
- **Title** (600, 19px): card titles (sensor name).
- **Body** (400, 15px, 1.4): default text. 16px (1.55) for tabs, chat and empty-state copy.
- **Label** (600, 14px, 0.08em, uppercase): panel headings only, in muted text above a hairline.
- **Caption** (400, 14px): organ names, notes, sources, footer legend.
- **Mono** (400, 14px, tabular): ages ("2 s ago"), timestamps, axis ticks, track end values, UTC clock. Units sit in Mono 18px muted beside the value; stats in Mono 500 22px.

### Named Rules
**The Mono Measures Rule.** If it was measured or timed (unit, age, axis, clock, raw dimension), set it in Plex Mono with tabular figures. The headline reading value stays in Plex Sans 500 tabular.

**The 14px Floor Rule.** No text below 14px, including chart ticks and SVG labels.

## Layout

Fixed window frame: 60px header band, 52px tab bar, scrolling main area with 20px padding, 40px footer carrying the state legend. Spacing is a 4px scale (4, 8, 12, 16, 20, 24, 32, 40); the default gap between blocks is 16px, between large grid columns 20px. Cards and panels are inset 16px vertical and 18px horizontal.

Screens are fixed grids sized for 1280px: Status uses 370px side columns around a flexible body map; Muscle a 390px side column; Urine a flexible column plus a column up to 600px; Assistant a flexible chat plus a 330px side panel. Below 1150px (the 1024px minimum window) side columns shrink (300px, 320px, 420px) and the header clock hides. Not designed for mobile. Interactive targets are at least 44px tall.

## Elevation & Depth

Flat. Depth comes from three navy steps (bg, surface, surface-2) and 1px lines (border for frames, rule for interior hairlines). There are no drop shadows. The only box-shadows are inset 1–2px lines used as drawn rules: the 2px underline of the active segmented button and the 1px end ticks of the range-track bracket.

### Named Rules
**The Flat Instrument Rule.** Surfaces never lift. Emphasis comes from state borders, the alert fill, or a tonal step, never from a shadow or glow.

## Shapes

Tight, near-square corners: 4px on containers (cards, panels, banners, table frame, info boxes), 3px on controls (buttons, inputs, selects, swatches, triage), 2px on tags and small frames (status pills, PROV. tag, segmented control, header controls, chat bubbles). Nothing is pill-shaped or circular except chart end markers and the "normal" icon. Borders are 1px by default; state borders are 2px (3px for the double no-range border). Status icons are drawn 16px SVG shapes: filled triangle with cut-out "!" for alert, circled check, circled clock, circled dash, diamond.

### Named Rules
**The Squared Tag Rule.** No radius above 4px anywhere; status tags are squared (2px).

## Components

### Buttons
Compact and decisive.
- **Shape:** gently squared (3px), 44px tall, 18px side padding, 15px semibold.
- **Primary:** Instrument Blue fill with Deep Space Navy text.
- **Ghost:** transparent with a 1px Frame Line border, Panel White text, regular weight.
- **On alert:** white fill with Alert Fill text, used only inside the attention banner.
- **Disabled:** 50% opacity. **Focus:** 2px Instrument Blue outline, 2px offset (global).

### Status Pills
- **Style:** 14px semibold, 2px corners, icon + label, padding 4px 11px 4px 9px.
- **States:** alert is filled (Alert Fill, white text, cut-out icon); normal is a 1.5px green outline; old data dashed amber; no data dotted gray with muted text; no range double sky; doubtful sample solid muted.

### Cards / Containers
- **Corner Style:** 4px.
- **Background:** Panel Navy; alert cards take the Alert Wash.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px Frame Line at rest; replaced by the state border pattern.
- **Internal Padding:** 16px 18px. Stale and no-data cards dim their value to Faint Label.
- **Panels:** same frame; the head is a 52px row with an uppercase Label heading over a Hairline, inset 18px.

### Inputs / Fields
- **Style:** 1px Frame Line, 3px corners, Deep Space Navy fill (chat) or Panel Navy (Records selects), 44–46px tall, 14px side padding.
- **Focus:** global 2px Instrument Blue outline; caret in Instrument Blue.

### Navigation
- **Header band:** brand mark + "Biomedical console" (18px semibold), a 1px white-mixed divider, crew selector and connection status in 2px-corner white-mixed outlines, UTC clock in Mono. Offline swaps to a 2px coral border.
- **Tab bar:** Panel Navy, 52px; tabs 16px muted, active tab Panel White semibold with a 2px Instrument Blue underline; a tab carries a state icon when its readings need attention.
- **Footer:** the state legend (icon + label for each state) and the PROV. note, 14px muted.

### Segmented Control
A 1px-framed strip with hairline separators; buttons 42px plus frame (44px target), 14px muted; active is Panel White semibold on a 9% white wash with a 2px inset underline.

### Range Track (signature)
A 2px rail with the normal span bracketed: 1px green end ticks, 10% green fill, 55% green center line. A needle with a cap marks the current value; the cap points down (triangle) on alert, becomes a diamond on no range, and turns dashed faint on old data; no needle on no data. End values in Mono faint; the range text centered between them with its PROV. tag and source.

### Instrument Line Chart (signature)
Hand-drawn SVG that keeps its CSS size at any width. Y ticks from a round-number scale (1, 2, 2.5, 5 × 10ⁿ), never past a physical cap (SpO₂ 100%); X ticks in UTC (times under two days, dates beyond). Grid in Hairline, axis in Faint Label, ticks Mono 14px. The normal zone is a 5% green tint with 60% green edge lines; edge values are printed in green in the right margin. The trace is Panel White at 1.5px and is drawn in Alert Coral only where it sits outside the zone. The line breaks at gaps (more than 3× the median interval) instead of bridging missing data. The last value is a Mono 500 label in the right margin with a faint leader, moved off the zone edge labels; the end marker repeats the state shape (circle, triangle, diamond, dashed hollow circle for old data). Optional: 3px square points for sparse series, a dotted baseline.

### Named Rules
**The Instrument Chart Rule.** Charts read like gauges: round ticks, zone edges labelled in the margin, one near-white trace, red only outside the zone, gaps left as gaps, the last value in Mono.

## Do's and Don'ts

### Do:
- **Do** pair every state color with its drawn icon, its text label and its border pattern (Three-Channel State Rule).
- **Do** set units, ages, axes and clocks in Plex Mono with tabular figures, and keep all text at 14px or above.
- **Do** keep corners at 4px (containers), 3px (controls), 2px (tags).
- **Do** build depth from bg / surface / surface-2 and 1px border or rule lines.
- **Do** draw new charts with the instrument grammar: niceScale ticks, 5% zone tint with edge values in the margin, 1.5px near-white trace that turns coral only outside the zone, breaks at gaps, Mono last-value label.
- **Do** keep the blue band and red rule as the only brand surface, in the header.
- **Do** keep interactive targets at least 44px tall.

### Don't:
- **Don't** convey a state by color alone, or tint a normal reading anything but green.
- **Don't** use red for decoration, emphasis or brand fills outside the header rule; red means out of bounds.
- **Don't** add drop shadows, glows or gradients for elevation.
- **Don't** round corners past 4px or make status tags pill-shaped.
- **Don't** bridge missing data in a chart or show an old value as if it were current; dim it and mark it.
- **Don't** use text glyphs (arrows, ×) as icons; draw them as SVG like the state icons.
