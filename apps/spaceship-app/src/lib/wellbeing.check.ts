// Self-check for lib/wellbeing.ts. Run: node src/lib/wellbeing.check.ts
import type { ComponentState, CrewMemberSummary, Origin, WellbeingAssessment } from "../api/types";
import {
  barFraction,
  componentLabel,
  formatDay,
  formatDayLong,
  formatValue,
  formatZ,
  missionDay,
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

console.log("wellbeing.check: ok");
