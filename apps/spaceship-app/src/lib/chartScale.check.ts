// Self-check for components/chartScale.ts. Run: node src/lib/chartScale.check.ts
import { niceScale, splitGaps, stepDecimals } from "../components/chartScale.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

// Heart rate 100–140 with range 60–100: round ticks, no 63.4.
const hr = niceScale([104, 141, 112], [60, 100], null, 5);
eq(hr.ticks, [50, 75, 100, 125, 150], "heart rate ticks");
eq(hr.ticks.every((t) => t % hr.step === 0), true, "ticks on step");

// SpO₂ 94–97 with range 95–100: the axis stops at the 100 % cap.
const spo2 = niceScale([94, 97, 96], [95, 100], 100);
eq(spo2.hi, 100, "spo2 capped");
eq(Math.max(...spo2.ticks) <= 100, true, "no tick above 100");
eq(spo2.ticks, [94, 96, 98, 100], "spo2 ticks");

// A value beyond the cap (bad data) is still inside the domain.
eq(niceScale([101], [95, 100], 100).hi >= 101, true, "bad data still drawn");

// Flat series: a non-empty domain around the value.
const flat = niceScale([38, 38, 38], []);
eq(flat.lo < 38 && flat.hi > 38, true, "flat series has height");
eq(flat.ticks.length >= 2, true, "flat series has ticks");

eq(niceScale([], []).ticks, [0, 0.5, 1], "empty");
eq([stepDecimals(20), stepDecimals(2.5), stepDecimals(0.25), stepDecimals(0.1)], [0, 1, 2, 1], "decimals");

// Gaps: a break where the interval is > 3× the median.
const pts = [0, 5, 10, 15, 60, 65].map((t) => ({ t, v: 1 }));
eq(splitGaps(pts).map((r) => r.length), [4, 2], "gap split");
eq(splitGaps(pts.slice(0, 2)).length, 1, "two points, one run");

// 14 daily points plus a burst of 20 two-minute samples stay one run with a 1.5-day floor.
const DAY = 86_400_000;
const burst = [
  ...Array.from({ length: 14 }, (_, i) => ({ t: i * DAY, v: 1 })),
  ...Array.from({ length: 20 }, (_, i) => ({ t: 14 * DAY + i * 120_000, v: 1 })),
];
eq(splitGaps(burst, 3, 1.5 * DAY).length, 1, "burst keeps daily line");
eq(splitGaps([...burst, { t: 20 * DAY, v: 1 }], 3, 1.5 * DAY).length, 2, "missing days still break");

console.log("chartScale.check: ok");
