import { formatNumber } from "../lib/format";
import { linear, yDomain, type Point } from "./chartScale";

interface Props {
  points: Point[];
  windowStart: number;
  windowEnd: number;
  normalMin: number | null;
  normalMax: number | null;
  label: string;
  emptyText: string;
}

const W = 560;
const H = 200;
const PAD_L = 44;
const PAD_R = 10;
const PAD_T = 12;
const PAD_B = 24;

/** Oscilloscope-style trace over a fixed time window, with dashed range guides. */
export function ScopeChart({
  points,
  windowStart,
  windowEnd,
  normalMin,
  normalMax,
  label,
  emptyText,
}: Props) {
  const inWindow = points.filter((p) => p.t >= windowStart && p.t <= windowEnd);
  const [y0, y1] = yDomain(
    inWindow.map((p) => p.v),
    [normalMin, normalMax],
  );
  const x = linear(windowStart, windowEnd, PAD_L, W - PAD_R);
  const y = linear(y0, y1, H - PAD_B, PAD_T);

  const gridX = [0, 1, 2, 3, 4, 5].map((i) => PAD_L + ((W - PAD_L - PAD_R) * i) / 5);
  const gridY = [0, 1, 2, 3].map((i) => PAD_T + ((H - PAD_T - PAD_B) * i) / 3);
  const minutes = Math.round((windowEnd - windowStart) / 60000);
  const ticks = [0, 1, 2, 3].map((i) => {
    const m = minutes - (minutes * i) / 3;
    return { x: x(windowEnd - m * 60000), text: m === 0 ? "ahora" : `−${formatNumber(m, 0)} min` };
  });

  const path = inWindow.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");

  return (
    <svg
      className="chart chart--scope"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${label}: ${inWindow.length} lecturas en la ventana`}
    >
      <rect className="chart__frame" x={PAD_L} y={PAD_T} width={W - PAD_L - PAD_R} height={H - PAD_T - PAD_B} />
      {gridX.map((gx) => (
        <line key={`gx${gx}`} className="chart__grid" x1={gx} x2={gx} y1={PAD_T} y2={H - PAD_B} />
      ))}
      {gridY.map((gy) => (
        <line key={`gy${gy}`} className="chart__grid" x1={PAD_L} x2={W - PAD_R} y1={gy} y2={gy} />
      ))}
      {[normalMax, normalMin].map((g, i) =>
        g === null ? null : (
          <g key={`guide${i}`}>
            <line className="chart__guide" x1={PAD_L} x2={W - PAD_R} y1={y(g)} y2={y(g)} />
            <text className="chart__label" x={PAD_L - 6} y={y(g) + 4} textAnchor="end">
              {formatNumber(g)}
            </text>
          </g>
        ),
      )}
      {ticks.map((t) => (
        <text key={t.text} className="chart__label" x={t.x} y={H - 6} textAnchor="middle">
          {t.text}
        </text>
      ))}
      {inWindow.length > 1 ? <polyline className="chart__trace" points={path} /> : null}
      {inWindow.map((p, i) => (
        <circle key={`${p.t}-${i}`}className="chart__dot" cx={x(p.t)} cy={y(p.v)} r={2.2} />
      ))}
      {inWindow.length === 0 ? (
        <text className="chart__empty" x={(W + PAD_L) / 2} y={H / 2} textAnchor="middle">
          {emptyText}
        </text>
      ) : null}
    </svg>
  );
}
