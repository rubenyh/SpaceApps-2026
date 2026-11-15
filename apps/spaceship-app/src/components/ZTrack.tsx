import { formatZ, zPercent, Z_MAX, Z_MIN } from "../lib/wellbeing";

interface Props {
  z: number | null;
  threshold: number;
  min?: number;
  max?: number;
  /** Old data: dimmed track, hollow dashed marker. */
  stale?: boolean;
}

/**
 * Distance from the person's own usual on a fixed z scale. The usual band runs from 0 to the
 * threshold; the dashed line is the threshold. Beyond it the marker turns amber (shape stays).
 */
export function ZTrack({ z, threshold, min = Z_MIN, max = Z_MAX, stale = false }: Props) {
  if (z === null) {
    return <div className="ztrack ztrack--empty" role="img" aria-label="No value" />;
  }
  const zero = zPercent(0, min, max);
  const edge = zPercent(threshold, min, max);
  const beyond = z >= threshold;
  const cls = `ztrack${stale ? " ztrack--stale" : ""}`;
  return (
    <div
      className={cls}
      role="img"
      aria-label={`z ${formatZ(z)}, ${beyond ? "beyond" : "within"} threshold ${threshold}`}
    >
      <span className="ztrack__zone" style={{ left: `${zero}%`, width: `${edge - zero}%` }} />
      <span className="ztrack__threshold" style={{ left: `${edge}%` }} />
      <span
        className={`ztrack__marker${beyond ? " ztrack__marker--beyond" : ""}`}
        style={{ left: `${zPercent(z, min, max)}%` }}
      />
    </div>
  );
}
