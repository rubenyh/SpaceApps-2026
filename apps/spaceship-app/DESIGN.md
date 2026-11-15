---
name: Biomedical console
description: Onboard astronaut health console in the ground console's split-flap identity: steel and flap surfaces, Barlow Condensed, red and amber states that never rely on colour alone.
colors:
  steel: "#15171a"
  flap: "#0b0b0d"
  housing: "#1c1e22"
  frame: "#2a2d31"
  steel-mid: "#5b5e63"
  label: "#a7aaaf"
  letter: "#f2f2f2"
  amber: "#ffb000"
  red: "#c8452f"
  on-red: "#ffffff"
  range-zone: "rgb(242 242 242 / 0.06)"
typography:
  data:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "0.04em"
    fontFeature: "tnum"
  headline-lg:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    letterSpacing: "0.08em"
  headline:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    letterSpacing: "0.04em"
  title:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    letterSpacing: "0.12em"
  nav:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    letterSpacing: "0.1em"
  body:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.35
    fontFeature: "tnum"
  label:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    letterSpacing: "0.1em"
  caption:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    letterSpacing: "0.08em"
    fontFeature: "tnum"
rounded:
  sm: "2px"
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
  sidebar:
    backgroundColor: "{colors.steel}"
    textColor: "{colors.letter}"
    width: "208px"
  nav-item:
    textColor: "{colors.label}"
    typography: "{typography.nav}"
    height: "44px"
    padding: "0 20px"
  nav-item-active:
    textColor: "{colors.letter}"
    typography: "{typography.nav}"
    height: "44px"
    padding: "0 20px"
  topbar:
    backgroundColor: "{colors.steel}"
    textColor: "{colors.letter}"
    typography: "{typography.title}"
    height: "56px"
    padding: "0 24px"
  button:
    backgroundColor: "{colors.flap}"
    textColor: "{colors.letter}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.letter}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 16px"
  button-on-alert:
    backgroundColor: "{colors.letter}"
    textColor: "{colors.flap}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 16px"
  chip-alert:
    backgroundColor: "{colors.red}"
    textColor: "{colors.on-red}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-stale:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.flap}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  chip-muted:
    backgroundColor: "transparent"
    textColor: "{colors.label}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  card:
    backgroundColor: "{colors.flap}"
    textColor: "{colors.letter}"
    rounded: "{rounded.sm}"
    padding: "16px"
  panel-heading:
    textColor: "{colors.letter}"
    typography: "{typography.label}"
    height: "48px"
  flap-plate:
    backgroundColor: "{colors.steel}"
    textColor: "{colors.letter}"
    typography: "{typography.data}"
    rounded: "{rounded.sm}"
  banner-alert:
    backgroundColor: "{colors.red}"
    textColor: "{colors.on-red}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  banner-stale:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.flap}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
  input-chat:
    backgroundColor: "{colors.flap}"
    textColor: "{colors.letter}"
    rounded: "{rounded.sm}"
    height: "46px"
    padding: "0 14px"
  select:
    backgroundColor: "{colors.flap}"
    textColor: "{colors.letter}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 40px 0 12px"
  segmented-button:
    backgroundColor: "{colors.flap}"
    textColor: "{colors.label}"
    height: "42px"
    padding: "0 14px"
  segmented-button-active:
    backgroundColor: "{colors.flap}"
    textColor: "{colors.letter}"
    height: "42px"
    padding: "0 14px"
---

# Design System: Biomedical console

## Overview

**Creative North Star: "The Departure Board"**

The console shares one identity with the ground console (`apps/base-app`): a dark steel board where readings arrive on split-flap plates. It is laid out as a calm operations dashboard for a 1280×800 window (minimum 1024×700): a steel sidebar with the brand and seven navigation items, a 56px top bar, and a scrolling screen of flat flap-black cards. Nothing floats and nothing glows. Structure comes from 1px frame lines and a steel/flap/housing tonal step.

A healthy screen is monochrome: letter white on black, labels in grey. Colour is reserved for trouble. Red means out of bounds, amber means old data, and grey outline means no data or no range. Every state also carries a drawn icon and a text label, so the screen reads in grayscale. The split flap is the one expressive device, and it is spent only on key reading values.

Everything is set in Barlow Condensed (500/600/700) with tabular figures, including measures, ages, axes and clocks. Labels, navigation, buttons and headings are uppercase and tracked. Corners are a uniform 2px.

**Key Characteristics:**
- Sidebar navigation (208px) plus a 56px top bar; no header band, no footer.
- Steel page, flap-black cards, 1px frame lines, 2px corners, no shadows.
- Barlow Condensed only, tabular figures everywhere, uppercase tracked labels.
- Normal is plain letter white; red, amber and grey only for states, always with icon and text.
- Split-flap plates on key reading values only.
- Instrument-style line charts and range tracks in the same monochrome grammar.

## Colors

A near-black steel board with one white letter colour, one grey label colour, and two signal colours that appear only when something is wrong.

### Primary
- **Letter White** (letter): primary text, reading values, chart trace, range needle, active nav item and its inset bar, focus ring, selection fill, caret. Normal state uses this colour; there is no "normal" hue.

### Secondary
- **Signal Red** (red): out-of-bounds readings and failed services only. As a fill it carries white text (alert chip, attention banner, offline chip, immediate triage). As a foreground it is used only at large size: flap letters, 1px alert card border, chart trace outside the zone, alert markers and icons.
- **Old-Data Amber** (amber): stale data. As a fill it carries flap-black text (stale chip, stale banner); as a foreground it marks the stale age line, the dashed stale needle and the stale chart end marker.

### Neutral
- **Steel** (steel): page, sidebar, top bar, and the plate behind split-flap letters.
- **Flap Black** (flap): cards, panels, buttons, inputs, selects, segmented control, text on amber and on the white on-alert button.
- **Housing** (housing): inset blocks inside cards: chat bubbles, table heads, triage blocks.
- **Frame** (frame): every 1px card, panel and banner border, hairline dividers, chart grid, range rail, scrollbar thumb.
- **Steel Mid** (steel-mid): control borders (buttons, selects, segmented control, PROV. tag), chart axis, dashed chart zone edges, range-track end ticks, button pressed state.
- **Label Grey** (label): secondary text, units, ages, captions, inactive nav items, axis ticks, no-data and no-range chips and icons, dimmed stale and no-data values.
- **White On Red** (on-red): text on the red fill only.
- **Range Zone** (range-zone): the 6% white fill of the normal span on charts and range tracks.

### Named Rules
**The Plain Normal Rule.** A reading in range is letter white on flap black. Never tint normal green or any other hue; a calm screen has no colour.

**The Red Means Out Rule.** Red appears only for readings or services that are out of bounds. Small red text never sits on black: below flap size it goes on a red fill with white text.

**The Two-Channel State Rule.** Every reading state is shown by a drawn icon and a text label (ALERT, OLD DATA, NO DATA, NO RANGE). Colour is an extra channel, never the only one.

## Typography

**Display Font:** Barlow Condensed (with sans-serif)
**Body Font:** Barlow Condensed
**Label/Mono Font:** Barlow Condensed with tabular figures (no separate mono face)

**Character:** A narrow, engineered display face that reads like the lettering on a station board. Bundled weights 500/600/700 via @fontsource; 500 is the body weight, 700 the heaviest. `SpO<sub>2</sub>` is written with a `<sub>` because the face lacks the ₂ glyph.

### Hierarchy
- **Data** (600, 26px, 36px from 1200px, line-height 1.15, 0.04em, tabular): reading values on flap plates in cards.
- **Headline Large** (700, 28px, 0.08em, uppercase): whole-screen empty-state titles.
- **Headline** (700, 22px, 0.04em, uppercase): attention-banner title. Stats use 600 22px.
- **Title** (700, 18px, 0.12em, uppercase): top-bar screen title. Brand is 700 20px 0.08em uppercase; card titles 700 16px 0.1em uppercase.
- **Nav** (600, 16px, 0.1em, uppercase): sidebar navigation items.
- **Body** (500, 17px, line-height 1.35; 1.45 for chat and paragraphs): default text, chat, selects. 16px for secondary body.
- **Label** (700, 15px, 0.08–0.1em, uppercase): panel headings, buttons, segmented buttons, top-bar crew and clock (600).
- **Caption** (600, 14px, 0.06–0.08em): chips, ages, stat labels, axis ticks, notes. Uppercase on chips, ages and stat labels.

### Named Rules
**The 14px Floor Rule.** No text below 14px, including chart ticks and SVG labels.

**The Tracked Label Rule.** Anything that names rather than says (nav, headings, buttons, chips, ages, stat labels) is uppercase with 0.04–0.12em tracking at 600–700. Sentences stay sentence case.

**The Tabular Board Rule.** Every number is tabular (`font-variant-numeric: tabular-nums` on body), so values never jitter as they change.

## Layout

The window is a two-column grid: sidebar (208px; 168px below 1150px) spanning full height, and a right column of a 56px top bar over a scrolling main area with 24px padding. Screens stack blocks with a 24px gap; card grids gap 16px. Spacing is a 4px scale (4, 8, 12, 16, 20, 24, 32, 40). Cards are inset 16px.

Card grids auto-fit where the content is a set of equal readings (Vital signs: `minmax(360px, 1fr)`; Urine cards: `minmax(160px, 1fr)`). Fixed columns hold where a centre object anchors the screen: Status puts 370px reading columns around the body map (248px below 1150px); Muscle uses a 390px side column; Assistant a flexible chat beside a 330px panel. Top-bar connection chips wrap to two lines below 1500px instead of widening the page. Not designed for mobile. Every interactive target is at least 44px tall.

## Elevation & Depth

Flat. Depth comes from three tonal steps (steel page, flap cards, housing insets) and 1px frame lines. There are no drop shadows, glows or gradients. The only box-shadows are inset lines used as drawn marks: the 3px left bar of the active nav item, the 3px underline of the active segmented button, and the 1px steel-mid end ticks of the range-track zone.

### Named Rules
**The Flat Board Rule.** Surfaces never lift. Emphasis comes from a red border, a red or amber fill, or a split-flap plate, never from a shadow.

## Shapes

One corner: 2px on everything (cards, panels, banners, buttons, inputs, selects, chips, flap plates). Nothing is pill-shaped. Borders are 1px; state never changes border width or pattern, only the alert turns the border red. Status icons are drawn 16px SVG shapes (triangle with cut-out "!" for alert, circled clock, circled dash, diamond), with the alert "!" cut out in the colour behind it.

### Named Rules
**The Square Corner Rule.** No radius other than 2px anywhere.

## Components

### Buttons
Plain board switches.
- **Shape:** 2px corners, 44px tall, 16px side padding, Label type (700 15px uppercase tracked).
- **Default:** flap-black fill, 1px steel-mid border, letter text. Hover fills frame; pressed fills steel-mid.
- **Ghost:** transparent with a 1px frame border.
- **On alert:** letter-white fill with flap-black text, used only on the red attention banner.
- **Disabled:** 45% opacity. **Focus:** 2px letter-white outline, 2px offset (global).

### Chips (status pills)
- **Style:** 14px 700 uppercase, 0.08em, 2px corners, 1px border, icon + label, padding 2px 8px.
- **States:** alert is red fill with white text; old data is amber fill with flap-black text; no data, no range and doubtful sample are a grey outline with grey text. Normal shows no chip colour. Wellbeing pills follow the same mapping (needs support red fill, attention amber outline, stale amber fill, no data grey).

### Cards / Containers
One pattern for every card, panel, banner and info box.
- **Corner Style:** 2px.
- **Background:** flap black.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px frame; only the alert state turns it red. Stale and no-data cards dim the value to label grey and show the age in amber or grey.
- **Internal Padding:** 16px. Panels have a 48px head row with a Label heading over a frame hairline, inset 16px.
- **Banners:** alert is a red fill with white text and a white on-alert button; stale is an amber fill with dark text; service error is flap black with a red border and red icon.

### Split-Flap Plate (signature)
The key reading value in a reading card or sensor card sits on a steel plate with a 1px dark hinge line across its middle, in Data type. A changed value cascades character by character in 240ms; the cascade is skipped under reduced motion and for ticking values. Out-of-range values set the flap letters in red (large-text contrast). Loading uses blank flap tiles instead of a pulsing card. Tables, chat, wellbeing and every other text stay plain.

### Inputs / Fields
- **Style:** flap-black fill, 1px steel-mid border, 2px corners, 44–46px tall. Selects carry a drawn grey chevron and hover to a grey border.
- **Focus:** global 2px letter-white outline; caret in letter white.

### Navigation
- **Sidebar:** brand "Biomedical console" (700 20px uppercase) in a 56px cell over a frame line, then seven items: Status, Vital signs, Muscle, Urine, Assistant, Records, Wellbeing. Items are 44px tall, Nav type in label grey; hover and active turn letter white; active adds a 3px inset bar on the left. An item carries a red alert or amber stale icon when its readings need attention (Wellbeing never does). Vertical tablist with arrow-key roving focus; disabled at 60% opacity when no crew member is loaded.
- **Top bar:** screen title, crew selector, connection chips (1px frame outline; offline becomes the red fill with white text), UTC clock in 600 15px with the time in letter white.

### Segmented Control
A 1px steel-mid frame with steel-mid separators; buttons 42px plus frame (44px target), 15px 600 uppercase in label grey; active is letter white with a 3px inset underline.

### Range Track
A 2px frame rail with the normal span as a 6% white zone between 1px steel-mid end ticks. A 2px letter-white needle with a cap marks the value; on alert it turns red with a downward triangle cap, on no range a grey diamond cap, on old data a dashed amber needle; no needle on no data.

### Instrument Line Chart
Hand-drawn SVG. Grid in frame, axis in steel-mid, ticks 14px 600 in label grey from a round-number scale. The normal zone is a 6% white fill with dashed steel-mid edges and its edge values in the margin. The trace is letter white at 2px and turns red only where it leaves the zone. The line breaks at gaps (more than 3× the median interval) instead of bridging missing data. The last value is a 14px 600 letter-white label with a grey leader; the end marker repeats the state (red on alert, grey on no data or no range, dashed amber hollow on old data).

### Named Rules
**The Flap Is For Readings Rule.** Split-flap plates hold key reading values and their loading skeleton, nothing else.

**The Instrument Chart Rule.** Charts read like gauges: round ticks, zone edges in the margin, one white trace, red only outside the zone, gaps left as gaps.

## Do's and Don'ts

### Do:
- **Do** pair every state colour with its drawn icon and its text label (Two-Channel State Rule).
- **Do** keep normal readings letter white (#f2f2f2) on flap black (#0b0b0d).
- **Do** put small red or amber state text on a filled chip: red fill with white text, amber fill with dark text.
- **Do** build every card, panel and banner from the one pattern: flap fill, 1px frame border, 2px corners, no shadow; only alert turns the border red.
- **Do** set all text in Barlow Condensed with tabular figures, keep it at 14px or above, and uppercase-track labels, nav, headings, buttons and chips.
- **Do** keep interactive targets at least 44px tall and the 2px letter-white focus outline visible.
- **Do** honour `prefers-reduced-motion`: no alert pulse and no flap cascade.
- **Do** draw new charts with the instrument grammar: round ticks, 6% zone with dashed edges, 2px white trace that turns red only outside the zone, breaks at gaps.

### Don't:
- **Don't** convey a state by colour alone, and don't tint a normal reading green or any hue.
- **Don't** use red or amber for decoration, emphasis, brand or navigation.
- **Don't** add drop shadows, glows or gradients for elevation.
- **Don't** use any corner radius other than 2px, or pill-shaped tags.
- **Don't** put split-flap plates on anything other than key reading values.
- **Don't** vary border style or width by state (no dashed, dotted or double borders on cards).
- **Don't** bridge missing data in a chart or show an old value as if it were current; dim it and mark it.
- **Don't** use text glyphs (arrows, ×) as icons; draw them as SVG like the state icons.
