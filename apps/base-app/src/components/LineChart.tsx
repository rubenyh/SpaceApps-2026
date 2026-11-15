import { niceScale } from "../lib/chart.ts";
import { formatNumber, utcDay, utcMinutes } from "../lib/format";

export interface Point {
  /** Epoch ms. */
  t: number;
  v: number;
}

interface Props {
  points: Point[];
  /** Visible time window, epoch ms. */
  start: number;
  end: number;
  normalMin?: number | null;
  normalMax?: number | null;
  /** viewBox width; narrower charts keep their text readable when scaled. */
  width?: number;
  /** Physical maximum of the axis, e.g. 100 for SpO₂ in %. */
  cap?: number | null;
  /** Draw every point (sparse series over days). */
  showPoints?: boolean;
  label: string;
  emptyText: string;
}

const H = 190;
const X0 = 44;
const Y0 = H - 28;
const Y1 = 10;
const DAY = 86_400_000;

const linear = (d0: number, d1: number, r0: number, r1: number) => {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v: number) => r0 + (v - d0) * k;
};

/** Hand-drawn SVG line chart: grid, range band, line. Times in UTC. */
export function LineChart({
  points,
  start,
  end,
  normalMin = null,
  normalMax = null,
  width: W = 560,
  cap = null,
  showPoints = false,
  label,
  emptyText,
}: Props) {
  const X1 = W - 12;
  const visible = points.filter((p) => p.t >= start && p.t <= end);
  const { lo, hi, ticks: yTicks } = niceScale(
    visible.map((p) => p.v),
    [normalMin, normalMax],
    cap,
  );
  const x = linear(start, end, X0, X1);
  const y = linear(lo, hi, Y0, Y1);
  const span = end - start;
  const xTicks = [0, 1, 2, 3].map((i) => start + (span * i) / 3);
  const tick = (t: number) => (span <= 2 * DAY ? utcMinutes(t) : utcDay(t));
  const hasZone = normalMin !== null || normalMax !== null;
  const zoneTop = y(normalMax ?? hi);
  const zoneBottom = y(normalMin ?? lo);
  const last = visible[visible.length - 1];

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}: ${visible.length} lecturas`}>
      {hasZone ? (
        <>
          <rect className="chart__zone" x={X0} y={zoneTop} width={X1 - X0} height={Math.max(0, zoneBottom - zoneTop)} />
          {[normalMax, normalMin].map((g, i) =>
            g === null ? null : <line key={i} className="chart__edge" x1={X0} x2={X1} y1={y(g)} y2={y(g)} />,
          )}
        </>
      ) : null}
      {yTicks.map((v) => (
        <g key={`y${v}`}>
          <line className="chart__grid" x1={X0} x2={X1} y1={y(v)} y2={y(v)} />
          {visible.length > 0 ? (
            <text className="chart__tick" x={X0 - 8} y={y(v) + 5} textAnchor="end">
              {formatNumber(v, 1)}
            </text>
          ) : null}
        </g>
      ))}
      {xTicks.map((t, i) => (
        <text
          key={`x${i}`}
          className="chart__tick"
          x={x(t)}
          y={H - 6}
          textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}
        >
          {tick(t)}
        </text>
      ))}
      {visible.length > 1 ? (
        <polyline
          className="chart__line"
          points={visible.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")}
        />
      ) : null}
      {showPoints
        ? visible.map((p, i) => <rect key={i} className="chart__point" x={x(p.t) - 3} y={y(p.v) - 3} width={6} height={6} />)
        : null}
      {last ? <rect className="chart__end" x={x(last.t) - 5} y={y(last.v) - 5} width={10} height={10} /> : null}
      {visible.length === 0 ? (
        <text className="chart__empty" x={(X0 + X1) / 2} y={(Y0 + Y1) / 2 + 6} textAnchor="middle">
          {emptyText}
        </text>
      ) : null}
    </svg>
  );
}
