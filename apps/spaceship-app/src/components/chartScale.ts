export interface Point {
  /** Epoch ms. */
  t: number;
  v: number;
}

/** Y scale with round-number ticks (1, 2, 2.5, 5 × 10ⁿ) covering data and range edges. */
export interface Scale {
  lo: number;
  hi: number;
  ticks: number[];
  step: number;
}

function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}

/**
 * Copied from apps/base-app/src/lib/chart.ts (plus `step` in the result).
 * `cap` is a physical maximum the axis does not round past (SpO₂ cannot pass 100 %).
 * Aims for about `count` ticks; the domain ends on ticks.
 */
export function niceScale(values: number[], guides: (number | null)[], cap: number | null = null, count = 4): Scale {
  const all = [...values, ...guides.filter((g): g is number => g !== null)];
  if (all.length === 0) return { lo: 0, hi: 1, ticks: [0, 0.5, 1], step: 0.5 };
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (lo === hi) {
    const p = Math.abs(lo) * 0.05 || 1;
    lo -= p;
    hi += p;
  }
  const step = niceStep((hi - lo) / (count - 1));
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  // The cap trims rounding headroom only; a value beyond it (bad data) is still drawn.
  if (cap !== null && hi > cap) hi = Math.max(cap, ...values);
  if (lo >= hi) lo = hi - step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 1e6; v += step) ticks.push(+(Math.round(v / step) * step).toFixed(10));
  return { lo, hi, ticks, step };
}

/** Decimals needed to print every tick of this step (2.5 → 1, 0.25 → 2, 10 → 0). */
export function stepDecimals(step: number): number {
  for (let d = 0; d < 6; d++) {
    const s = step * 10 ** d;
    if (Math.abs(Math.round(s) - s) < 1e-6) return d;
  }
  return 6;
}

export function linear(d0: number, d1: number, r0: number, r1: number) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (x: number) => r0 + (x - d0) * k;
}

/** Splits a time series where a gap is more than `factor` × the median interval (and at least `minGap`). */
export function splitGaps(points: Point[], factor = 3, minGap = 0): Point[][] {
  if (points.length < 3) return points.length ? [points] : [];
  const gaps = points
    .slice(1)
    .map((p, i) => p.t - points[i].t)
    .sort((a, b) => a - b);
  const limit = Math.max(gaps[Math.floor(gaps.length / 2)] * factor, minGap);
  const runs: Point[][] = [[points[0]]];
  for (let i = 1; i < points.length; i++) {
    if (points[i].t - points[i - 1].t > limit) runs.push([]);
    runs[runs.length - 1].push(points[i]);
  }
  return runs;
}
