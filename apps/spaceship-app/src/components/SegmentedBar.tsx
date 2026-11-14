interface Props {
  value: number | null;
  normalMin: number | null;
  normalMax: number | null;
  segments?: number;
  /** Accessible description. */
  label: string;
}

/**
 * Segmented level bar. The scale extends the normal range by half its width
 * on each side; segments inside the normal range carry a tick underneath.
 * Without a complete range nothing is drawn (no invented scale).
 */
export function SegmentedBar({ value, normalMin, normalMax, segments = 16, label }: Props) {
  if (normalMin === null || normalMax === null || normalMax <= normalMin) {
    return <div className="segbar segbar--none">SIN RANGO · sin escala</div>;
  }
  const span = normalMax - normalMin;
  const lo = normalMin - span / 2;
  const hi = normalMax + span / 2;
  const step = (hi - lo) / segments;
  const filled =
    value === null ? 0 : Math.max(0, Math.min(segments, Math.round((value - lo) / step)));

  const cells = Array.from({ length: segments }, (_, i) => {
    const center = lo + step * (i + 0.5);
    const inRange = center >= normalMin && center <= normalMax;
    const on = i < filled;
    return (
      <span
        key={i}
        className={`segbar__cell${on ? " segbar__cell--on" : ""}${inRange ? " segbar__cell--range" : ""}`}
      />
    );
  });

  return (
    <div
      className="segbar"
      role="img"
      aria-label={value === null ? `${label}: sin valor` : `${label}: ${filled} de ${segments}`}
    >
      <div className="segbar__cells">{cells}</div>
      <div className="segbar__legend">marcas inferiores = rango normal</div>
    </div>
  );
}
