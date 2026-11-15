// shortcut: copied from apps/base-app, no shared package between the apps; extract if a third copy appears

const FLAP_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÑ0123456789.-:#";

/**
 * Intermediate strings for a split-flap change from `from` to `to`.
 * Only changed positions flip; they settle left to right. The last frame is `to`.
 * At most `maxFrames` frames so the whole cascade stays short.
 */
export function cascadeFrames(from: string, to: string, maxFrames = 8): string[] {
  const n = Math.max(from.length, to.length);
  const a = from.padEnd(n);
  const b = to.padEnd(n);
  const changed: number[] = [];
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) changed.push(i);
  if (changed.length === 0) return [];
  const frames = Math.min(maxFrames, changed.length + 1);
  const settle = new Map(changed.map((i, r) => [i, 1 + Math.ceil(((r + 1) * (frames - 1)) / changed.length)]));
  const out: string[] = [];
  for (let k = 1; k < frames; k++) {
    let s = "";
    for (let i = 0; i < n; i++) {
      const at = settle.get(i);
      if (at === undefined || k >= at) s += b[i];
      else s += FLAP_CHARS[(Math.max(0, FLAP_CHARS.indexOf(a[i].toUpperCase())) + k) % FLAP_CHARS.length];
    }
    out.push(s);
  }
  out.push(to);
  return out;
}
