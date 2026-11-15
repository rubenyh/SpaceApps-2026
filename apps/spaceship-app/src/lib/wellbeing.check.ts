// Self-check for lib/wellbeing.ts. Run: node src/lib/wellbeing.check.ts
import type { ComponentState, IndicatorState, CrewMemberSummary, Origin, WellbeingAssessment } from "../api/types";
import {
  addDays,
  barFraction,
  baselineDays,
  indicatorScored,
  dayCount,
  validPeriod,
  componentLabel,
  formatDay,
  formatDayLong,
  formatValue,
  formatZ,
  missionDay,
  snapToStep,
  staleHint,
  supportSuggestion,
  videoLogZ,
  zPercent,
} from "./wellbeing.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

eq(formatZ(null), "---", "missing z");
eq(formatZ(2.44), "+2.4", "positive z");
eq(formatZ(-0.2), "−0.2", "negative z uses a true minus");
eq(formatZ(-0.04), "0.0", "no signed zero");

eq(zPercent(-2), 0, "track start");
eq(zPercent(4), 100, "track end");
eq(zPercent(1), 50, "track middle");
eq(zPercent(9), 100, "clamped high");
eq(zPercent(-5), 0, "clamped low");

eq(barFraction(2), 0.5, "bar half");
eq(barFraction(6), 1, "bar capped at z 4");
eq(barFraction(-1), 0, "no negative bar");

eq(formatDay("2026-11-07"), "Nov 7", "short day");
eq(formatDayLong("2026-11-07"), "Sat, Nov 7", "long day");
eq(missionDay("America/Tijuana", new Date("2026-11-15T03:00:00Z")), "2026-11-14", "mission day in zone");
eq(addDays("2026-11-14", -20), "2026-10-25", "add days back");
eq(addDays("2026-02-28", 1), "2026-03-01", "add days over month end");
eq(dayCount("2026-10-25", "2026-11-14"), 21, "inclusive day count");
eq(dayCount("2026-11-14", "2026-11-14"), 1, "single day");
eq(validPeriod("2026-10-25", "2026-11-14", "2026-11-14"), true, "period ok");
eq(validPeriod("2026-11-15", "2026-11-14", "2026-11-20"), false, "from after to");
eq(validPeriod("2026-11-01", "2026-11-15", "2026-11-14"), false, "period in the future");
eq(validPeriod("", "2026-11-14", "2026-11-14"), false, "empty from");
eq(snapToStep(7.3, 0, 24, 0.5), 7.5, "snap up to half hour");
eq(snapToStep(7.2, 0, 24, 0.5), 7, "snap down to half hour");
eq(snapToStep(30, 0, 24, 0.5), 24, "clamp high");
eq(snapToStep(-1, 0, 24, 0.5), 0, "clamp low");
eq(snapToStep(0.1 + 0.2 + 0.5, 0, 24, 0.1), 0.8, "no float noise");

const member = (level: CrewMemberSummary["level"]): CrewMemberSummary => ({
  astronaut_id: "a",
  display_name: "Ana Sorensen",
  level,
  trend: "stable",
  latest_origin: null,
});
eq(supportSuggestion(member("ok")), null, "no suggestion when doing well");
eq(supportSuggestion(member("needs_support"))?.title, "Check in with Ana", "suggestion title");

const comp = (component: string, z: number | null, origin: Origin | null, day: string | null) =>
  ({ component, z, latest_origin: origin, latest_day: day }) as ComponentState;
const assessment = (fatigue: ComponentState[], stress: ComponentState[]) =>
  ({
    indicators: [
      { kind: "fatigue", components: fatigue },
      { kind: "stress", components: stress },
    ],
  }) as unknown as WellbeingAssessment;
const today = "2026-11-14";
eq(
  videoLogZ(
    assessment(
      [comp("checkin.energy", 3, "live", today), comp("vision.perclos", -0.2, "live", today), comp("vision.yawns_per_min", 0.5, "live", today)],
      [comp("vision.brow_lower_delta", 1.9, "live", today), comp("signal.hrv_sdnn", 4, "live", today)],
    ),
    today,
  ),
  { fatigue: 0.5, tension: 1.9 },
  "video log: max of live vision components only",
);
eq(
  videoLogZ(assessment([comp("vision.perclos", 2, "simulated", today)], [comp("vision.brow_lower_peak_1s", 2, "live", "2026-11-13")]), today),
  null,
  "video log: nothing live today",
);
eq(
  videoLogZ(assessment([comp("vision.perclos", null, "live", today)], []), today),
  { fatigue: null, tension: null },
  "video log: live but no z",
);

eq(componentLabel("checkin.sleep_hours"), "sleep hours (check-in)", "component label check-in");
eq(componentLabel("vision.brow_lower_peak_1s"), "brow lower peak 1s (vision)", "component label vision");
eq(formatValue(null, "h"), "---", "missing value");
eq(formatValue(4.5, "h"), "4.5 h", "value with unit");
eq(formatValue(3, "0-4"), "3 / 4", "scale value");
eq(formatValue(0.6667, "ratio"), "0.67 ratio", "rounded value");


// Insufficient data / baseline pending never get a score.
{
  const comp = (baseline_days: number, baseline_ready: boolean) =>
    ({ baseline_days, baseline_ready }) as ComponentState;
  const ind = (status: IndicatorState["status"], z: number | null, comps: ComponentState[]) =>
    ({ status, z, components: comps }) as IndicatorState;
  eq(indicatorScored(ind("attention", 2.1, [comp(7, true)]), 5), true, "full baseline is scored");
  eq(indicatorScored(ind("ok", 0.2, [comp(4, true)]), 5), false, "baseline_days < min is not scored");
  eq(indicatorScored(ind("stale", 1.0, [comp(7, true)]), 5), false, "stale is not scored");
  eq(indicatorScored(ind("no_data", null, []), 5), false, "no_data is not scored");
  eq(indicatorScored(ind("baseline_pending", 0.5, [comp(3, false)]), 5), false, "pending is not scored");
  eq(baselineDays(ind("no_data", null, [])), 0, "no components = 0 baseline days");
  eq(baselineDays(ind("ok", 0, [comp(3, false), comp(6, true)])), 6, "largest component baseline");
}
eq(staleHint("2026-11-11", "2026-11-14"), "Last data Nov 11 — 3 days old.", "stale hint with age");
eq(staleHint("2026-11-13", "2026-11-14"), "Last data Nov 13 — 1 day old.", "stale hint singular");
eq(staleHint("2026-11-11"), "Last data Nov 11.", "stale hint without today");
eq(staleHint(null, "2026-11-14"), "Last data ---.", "stale hint without day");

console.log("wellbeing.check: ok");
