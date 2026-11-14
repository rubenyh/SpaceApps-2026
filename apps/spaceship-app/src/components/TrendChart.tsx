import { formatNumber, formatUtcDay, formatUtcTime } from "../lib/format";
import { linear, yDomain, type Point } from "./chartScale";

interface Props {
  points: Point[];
  start: number;
  end: number;
  normalMin?: number | null;
  normalMax?: number | null;
  label: string;
  emptyText: string;
}

const W = 760;
const H = 220;
const PAD_L = 52;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 26;
const DAY = 86_400_000;

/** Points joined by a line over days/weeks. Dates on the x axis are UTC. */
export function TrendChart({
  points,
  start,
  end,
  normalMin = null,
  normalMax = null,
  label,
  emptyText,
}: Props) {
  const visible = points.filter((p) => p.t >= start && p.t <= end);
  const values = visible.map((p) => p.v);
  const [y0, y1] = yDomain(values, [normalMin, normalMax]);
  const x = linear(start, end, PAD_L, W - PAD_R);
  const y = linear(y0, y1, H - PAD_B, PAD_T);

  const span = end - start;
  const tickCount = 6;
  const ticks = Array.from({ length: tickCount }, (_, i) => start + (span * i) / (tickCount - 1));
  const tickText = (t: number) => (span <= 2 * DAY ? formatUtcTime(t) : formatUtcDay(t));

  const yTicks = [y0, (y0 + y1) / 2, y1];
  const path = visible.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");

  return (
    <svg
      className="chart chart--trend"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${label}: ${visible.length} lecturas`}
    >
      <rect className="chart__frame" x={PAD_L} y={PAD_T} width={W - PAD_L - PAD_R} height={H - PAD_T - PAD_B} />
      {ticks.map((t) => (
        <g key={`t${t}`}>
          <line className="chart__grid" x1={x(t)} x2={x(t)} y1={PAD_T} y2={H - PAD_B} />
          <text className="chart__label" x={x(t)} y={H - 7} textAnchor="middle">
            {tickText(t)}
          </text>
        </g>
      ))}
      {visible.length > 0
        ? yTicks.map((v) => (
            <text key={`y${v}`} className="chart__label chart__label--dim" x={PAD_L - 6} y={y(v) + 4} textAnchor="end">
              {formatNumber(v, 1)}
            </text>
          ))
        : null}
      {[normalMax, normalMin].map((g, i) =>
        g === null ? null : (
          <line key={`guide${i}`} className="chart__guide" x1={PAD_L} x2={W - PAD_R} y1={y(g)} y2={y(g)} />
        ),
      )}
      {visible.length > 1 ? <polyline className="chart__trace" points={path} /> : null}
      {visible.map((p, i) => (
        <rect key={`${p.t}-${i}`}className="chart__marker" x={x(p.t) - 3} y={y(p.v) - 3} width={6} height={6} />
      ))}
      {visible.length === 0 ? (
        <text className="chart__empty" x={(W + PAD_L) / 2} y={H / 2} textAnchor="middle">
          {emptyText}
        </text>
      ) : null}
    </svg>
  );
}
