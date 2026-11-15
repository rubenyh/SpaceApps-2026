import type { ReadingStatus } from "../api/types";
import { formatNumber, formatUtcDay, formatUtcTime } from "../lib/format";
import { linear, yDomain, type Point } from "./chartScale";

interface Props {
  points: Point[];
  /** Visible time window, epoch ms. */
  start: number;
  end: number;
  normalMin?: number | null;
  normalMax?: number | null;
  /** Text inside the normal zone, e.g. "Normal 60–100 bpm · PROV.". */
  zoneLabel?: string;
  /** Status of the latest point: sets the shape of the end marker. */
  status?: ReadingStatus;
  /** Draw every point (sparse series over days or weeks). */
  showPoints?: boolean;
  /** Dotted reference line at this value, e.g. the first reading. */
  baseline?: number | null;
  /** viewBox size in px. The chart scales to its container width. */
  width?: number;
  height?: number;
  label: string;
  emptyText: string;
}

const X0 = 46;
const Y1 = 12;
const DAY = 86_400_000;
const X_TICKS = 4;
const Y_TICKS = 4;

function endMarker(status: ReadingStatus, x: number, y: number) {
  const cls = `linechart__end linechart__end--${status}`;
  if (status === "alert") {
    return (
      <path className={`${cls} alert-pulse`} d={`M${x},${y - 12} L${x + 10},${y + 6} L${x - 10},${y + 6} Z`} />
    );
  }
  if (status === "no_range") {
    return <path className={cls} d={`M${x},${y - 8} L${x + 8},${y} L${x},${y + 8} L${x - 8},${y} Z`} />;
  }
  return <circle className={cls} cx={x} cy={y} r={6} />;
}

/** Hand-written SVG line chart: grid, shaded normal zone, line and end marker. Times are UTC. */
export function LineChart({
  points,
  start,
  end,
  normalMin = null,
  normalMax = null,
  zoneLabel,
  status,
  showPoints = false,
  baseline = null,
  width: W = 564,
  height: H = 200,
  label,
  emptyText,
}: Props) {
  const X1 = W - 14;
  const Y0 = H - 30;
  const visible = points.filter((p) => p.t >= start && p.t <= end);
  const [lo, hi] = yDomain(
    visible.map((p) => p.v),
    [normalMin, normalMax, baseline],
  );
  const x = linear(start, end, X0, X1);
  const y = linear(lo, hi, Y0, Y1);
  const span = end - start;
  const xTicks = Array.from({ length: X_TICKS }, (_, i) => start + (span * i) / (X_TICKS - 1));
  const yTicks = Array.from({ length: Y_TICKS }, (_, i) => lo + ((hi - lo) * i) / (Y_TICKS - 1));
  const tickText = (t: number) => (span <= 2 * DAY ? formatUtcTime(t) : formatUtcDay(t));
  const last = visible[visible.length - 1];
  const hasZone = normalMin !== null || normalMax !== null;
  const zoneTop = y(normalMax ?? hi);
  const zoneBottom = y(normalMin ?? lo);

  return (
    <svg
      className="linechart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${label}: ${visible.length} readings`}
    >
      {yTicks.map((v) => (
        <g key={`y${v}`}>
          <line className="linechart__grid" x1={X0} x2={X1} y1={y(v)} y2={y(v)} />
          {visible.length > 0 ? (
            <text className="linechart__tick" x={X0 - 8} y={y(v) + 5} textAnchor="end">
              {formatNumber(v, 1)}
            </text>
          ) : null}
        </g>
      ))}
      {hasZone ? (
        <>
          <rect className="linechart__zone" x={X0} y={zoneTop} width={X1 - X0} height={zoneBottom - zoneTop} />
          {[normalMax, normalMin].map((g, i) =>
            g === null ? null : (
              <line key={i} className="linechart__zone-edge" x1={X0} x2={X1} y1={y(g)} y2={y(g)} />
            ),
          )}
          {zoneLabel ? (
            <text className="linechart__zone-label" x={X0 + 10} y={zoneTop + 19}>
              {zoneLabel}
            </text>
          ) : null}
        </>
      ) : null}
      {xTicks.map((t, i) => (
        <text
          key={`x${t}`}
          className="linechart__tick"
          x={x(t)}
          y={H - 8}
          textAnchor={i === 0 ? "start" : i === X_TICKS - 1 ? "end" : "middle"}
        >
          {tickText(t)}
        </text>
      ))}
      {baseline !== null && visible.length > 0 ? (
        <line className="linechart__baseline" x1={X0} x2={X1} y1={y(baseline)} y2={y(baseline)} />
      ) : null}
      {visible.length > 1 ? (
        <polyline
          className="linechart__line"
          points={visible.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")}
        />
      ) : null}
      {showPoints
        ? visible.map((p, i) => (
            <circle key={`${p.t}-${i}`} className="linechart__point" cx={x(p.t)} cy={y(p.v)} r={4} />
          ))
        : null}
      {last && status ? endMarker(status, x(last.t), y(last.v)) : null}
      {visible.length === 0 ? (
        <text className="linechart__empty" x={(X0 + X1) / 2} y={(Y0 + Y1) / 2} textAnchor="middle">
          {emptyText}
        </text>
      ) : null}
    </svg>
  );
}
