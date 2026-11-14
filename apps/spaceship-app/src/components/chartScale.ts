export interface Point {
  /** Epoch ms. */
  t: number;
  v: number;
}

/** Y domain covering the data and the guide lines, with a little padding. */
export function yDomain(values: number[], guides: (number | null)[]): [number, number] {
  const all = [...values, ...guides.filter((g): g is number => g !== null)];
  if (all.length === 0) return [0, 1];
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.05 || 1;
    lo -= pad;
    hi += pad;
  }
  const pad = (hi - lo) * 0.12;
  return [lo - pad, hi + pad];
}

export function linear(d0: number, d1: number, r0: number, r1: number) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (x: number) => r0 + (x - d0) * k;
}
