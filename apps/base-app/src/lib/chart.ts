/** Y scale with round-number ticks (1, 2, 2.5, 5 × 10ⁿ) covering data and range edges. */
export interface Scale {
  lo: number;
  hi: number;
  ticks: number[];
}

function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}

/**
 * `cap` is a physical maximum the axis does not round past (SpO₂ cannot pass 100 %).
 * Aims for about `count` ticks; the domain ends on ticks.
 */
export function niceScale(values: number[], guides: (number | null)[], cap: number | null = null, count = 4): Scale {
  const all = [...values, ...guides.filter((g): g is number => g !== null)];
  if (all.length === 0) return { lo: 0, hi: 1, ticks: [0, 0.5, 1] };
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
  return { lo, hi, ticks };
}
