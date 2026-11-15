import { useId, useLayoutEffect, useRef, useState } from "react";
import type { ReadingStatus } from "../api/types";
import { formatNumber, formatUtcDay, formatUtcTime } from "../lib/format";
import { dailyMean, linear, niceScale, splitGaps, stepDecimals, type Point } from "./chartScale";

interface Props {
  points: Point[];
  /** Visible time window, epoch ms. */
  start: number;
  end: number;
  normalMin?: number | null;
  normalMax?: number | null;
  /** Physical maximum the axis never rounds past (SpO₂ in %: 100). */
  cap?: number | null;
  /** Status of the latest point: sets the shape of the end marker. */
  status?: ReadingStatus;
  /** Draw every point (sparse series over days or weeks). */
  showPoints?: boolean;
  /** Dotted reference line at this value, e.g. the first reading. */
  baseline?: number | null;
  /** Fixed y-axis range; the top is also a cap. Data outside it still widens the axis. */
  yDomain?: [number, number];
  /** Design size in px. The chart takes its container width and keeps this aspect ratio. */
  width?: number;
  height?: number;
  label: string;
  emptyText: string;
}

const X0 = 50;
const Y1 = 12;
/** Right margin: zone edge values and the last-value label. */
const RIGHT = 62;
const DAY = 86_400_000;
const X_TICKS = 4;
const Y_TICKS = 5;
/** Vertical room one 14 px label needs. */
const LABEL_H = 16;

function endMarker(status: ReadingStatus, x: number, y: number) {
  const cls = `linechart__end linechart__end--${status}`;
  if (status === "alert") {
    return <path className={`${cls} alert-pulse`} d={`M${x},${y - 6} L${x + 5.5},${y + 4} L${x - 5.5},${y + 4} Z`} />;
  }
  if (status === "no_range") {
    return <path className={cls} d={`M${x},${y - 5} L${x + 5},${y} L${x},${y + 5} L${x - 5},${y} Z`} />;
  }
  return <circle className={cls} cx={x} cy={y} r={4} />;
}

/** Tracks the rendered width of the svg so text and strokes draw at their CSS size. */
function useWidth(initial: number) {
  const ref = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(initial);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const w = Math.round(e.contentRect.width);
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Hand-written SVG line chart: grid, normal zone, line and end marker. Times are UTC. */
export function LineChart({
  points,
  start,
  end,
  normalMin = null,
  normalMax = null,
  cap = null,
  status,
  showPoints = false,
  baseline = null,
  yDomain,
  width = 564,
  height = 200,
  label,
  emptyText,
}: Props) {
  const [ref, W] = useWidth(width);
  const H = Math.round((height * W) / width);
  const clipId = `lc${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const X1 = W - RIGHT;
  const Y0 = H - 30;
  const span = end - start;
  const inWindow = points.filter((p) => p.t >= start && p.t <= end);
  // Day-scale windows: live samples every few minutes would pile up at the right edge as a smear.
  const visible = span > 2 * DAY ? dailyMean(inWindow) : inWindow;
  const scale = niceScale(
    visible.map((p) => p.v),
    [normalMin, normalMax, baseline, ...(yDomain ?? [])],
    yDomain ? yDomain[1] : cap,
    // One more tick lands a 0-5 domain on whole steps (0, 1 … 5) instead of rounding up to 6.
    yDomain ? Y_TICKS + 1 : Y_TICKS,
  );
  const decimals = stepDecimals(scale.step);
  const x = linear(start, end, X0, X1);
  const y = linear(scale.lo, scale.hi, Y0, Y1);
  const xTicks = Array.from({ length: X_TICKS }, (_, i) => start + (span * i) / (X_TICKS - 1));
  const tickText = (t: number) =>
    span <= 2 * DAY ? formatUtcTime(t, span <= 10 * 60_000) : formatUtcDay(t);
  const last = visible[visible.length - 1];
  const hasZone = normalMin !== null || normalMax !== null;
  const zoneTop = y(normalMax ?? scale.hi);
  const zoneBottom = y(normalMin ?? scale.lo);

  // Zone edge values sit in the right margin; the last-value label moves off them, or hides them.
  const edges = [normalMax, normalMin]
    .filter((g): g is number => g !== null)
    .map((g) => ({ v: g, y: y(g), shown: true }));
  const clampY = (v: number) => Math.min(Math.max(v, Y1 + 4), Y0);
  let labelY = 0;
  if (last) {
    labelY = clampY(y(last.v));
    for (const e of edges) {
      if (Math.abs(labelY - e.y) < LABEL_H) labelY = labelY <= e.y ? e.y - LABEL_H : e.y + LABEL_H;
    }
    labelY = clampY(labelY);
    for (const e of edges) if (Math.abs(labelY - e.y) < LABEL_H) e.shown = false;
  }

  // A gap over 3× the median interval breaks the line instead of drawing across missing data.
  // On day-scale windows a burst of fresh samples must not turn every daily gap into a break.
  const linePath = splitGaps(visible, 3, span > 2 * DAY ? 1.5 * DAY : 0)
    .map(
      (run) =>
        run.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ") +
        (run.length === 1 ? " h0.01" : ""),
    )
    .join(" ");
  const marks = (
    <>
      {visible.length > 0 ? <path className="linechart__line" d={linePath} /> : null}
      {showPoints
        ? visible.map((p, i) => (
            <circle key={`${p.t}-${i}`} className="linechart__point" cx={x(p.t)} cy={y(p.v)} r={2.5} />
          ))
        : null}
    </>
  );

  return (
    <svg
      ref={ref}
      className="linechart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${label}: ${visible.length} readings`}
    >
      {hasZone ? (
        <defs>
          <clipPath id={`${clipId}-in`}>
            {/* 1px overlap: a reading on the edge is normal (inclusive) and must draw fully white. */}
            <rect x={0} y={zoneTop - 1} width={W} height={Math.max(zoneBottom - zoneTop + 2, 0)} />
          </clipPath>
          <clipPath id={`${clipId}-out`}>
            <rect x={0} y={0} width={W} height={Math.max(zoneTop - 1, 0)} />
            <rect x={0} y={zoneBottom + 1} width={W} height={Math.max(H - zoneBottom - 1, 0)} />
          </clipPath>
        </defs>
      ) : null}
      {scale.ticks.map((v) => (
        <g key={`y${v}`}>
          {y(v) < Y0 - 0.5 ? <line className="linechart__grid" x1={X0} x2={X1} y1={y(v)} y2={y(v)} /> : null}
          {visible.length > 0 ? (
            <text className="linechart__tick" x={X0 - 10} y={y(v) + 5} textAnchor="end">
              {v.toFixed(decimals)}
            </text>
          ) : null}
        </g>
      ))}
      {hasZone ? (
        <>
          <rect className="linechart__zone" x={X0} y={zoneTop} width={X1 - X0} height={zoneBottom - zoneTop} />
          {edges.map((e) => (
            <g key={e.v}>
              <line className="linechart__zone-edge" x1={X0} x2={X1} y1={e.y} y2={e.y} />
              {e.shown ? (
                <text className="linechart__edge" x={X1 + 12} y={e.y + 5}>
                  {formatNumber(e.v)}
                </text>
              ) : null}
            </g>
          ))}
        </>
      ) : null}
      <line className="linechart__axis" x1={X0} x2={X1} y1={Y0} y2={Y0} />
      {xTicks.map((t, i) => (
        <g key={`x${t}`}>
          <line className="linechart__axis" x1={x(t)} x2={x(t)} y1={Y0} y2={Y0 + 5} />
          <text
            className="linechart__tick"
            x={x(t)}
            y={H - 6}
            textAnchor={i === 0 ? "start" : i === X_TICKS - 1 ? "end" : "middle"}
          >
            {tickText(t)}
          </text>
        </g>
      ))}
      {baseline !== null && visible.length > 0 ? (
        <line className="linechart__baseline" x1={X0} x2={X1} y1={y(baseline)} y2={y(baseline)} />
      ) : null}
      {hasZone ? (
        <>
          <g clipPath={`url(#${clipId}-in)`}>{marks}</g>
          <g className="linechart__out" clipPath={`url(#${clipId}-out)`}>
            {marks}
          </g>
        </>
      ) : (
        marks
      )}
      {last ? (
        <g className="linechart__last">
          <polyline
            className="linechart__leader"
            points={`${x(last.t) + 7},${y(last.v)} ${X1 + 4},${y(last.v)} ${X1 + 9},${labelY}`}
          />
          <text x={X1 + 12} y={labelY + 5}>
            {formatNumber(last.v)}
          </text>
        </g>
      ) : null}
      {last && status ? endMarker(status, x(last.t), y(last.v)) : null}
      {visible.length === 0 ? (
        <text className="linechart__empty" x={(X0 + X1) / 2} y={(Y0 + Y1) / 2} textAnchor="middle">
          {emptyText}
        </text>
      ) : null}
    </svg>
  );
}
