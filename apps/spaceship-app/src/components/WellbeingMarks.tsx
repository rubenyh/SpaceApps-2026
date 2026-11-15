// Wellbeing marks: level pill, origin chip, trend, confidence. Never pulse; state is icon + text + border.
import type { Confidence, IndicatorStatus, Origin, SupportLevel, Trend } from "../api/types";
import {
  CONFIDENCE_LABELS,
  INDICATOR_STATUS_LABELS,
  SUPPORT_LABELS,
  TREND_LABELS,
} from "../lib/wellbeing";

const LINE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export type WellbeingGlyph = SupportLevel | "info" | "lock" | "chat" | "discrepancy" | "service_off";

function glyph(kind: WellbeingGlyph) {
  switch (kind) {
    case "ok":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...LINE} />
          <path d="M8 12.5l2.5 2.5L16 9.5" {...LINE} />
        </>
      );
    case "attention":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...LINE} />
          <path d="M7 13c1.5-2 3-2 5 0s3.5 2 5 0" {...LINE} />
        </>
      );
    case "needs_support":
      // A heart, not the physical alert triangle: support, not alarm.
      return <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" {...LINE} />;
    case "baseline_pending":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...LINE} strokeDasharray="2 3" />
          <circle cx="12" cy="12" r="3" {...LINE} />
        </>
      );
    case "stale":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...LINE} />
          <path d="M12 7v5l3 2" {...LINE} />
        </>
      );
    case "no_data":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...LINE} strokeDasharray="2 3" />
          <path d="M8 16l8-8" {...LINE} />
        </>
      );
    case "info":
      return (
        <>
          <circle cx="12" cy="12" r="9" {...LINE} />
          <path d="M12 8h.01M11 12h1v5h1" {...LINE} />
        </>
      );
    case "lock":
      return (
        <>
          <rect x="5" y="11" width="14" height="9" rx="2" {...LINE} />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" {...LINE} />
        </>
      );
    case "chat":
      return <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" {...LINE} />;
    case "discrepancy":
      return <path d="M4 12h6M14 12h6M10 8l-4 4 4 4M14 8l4 4-4 4" {...LINE} />;
    case "service_off":
      return <path d="M4 4l16 16M9 5h9a2 2 0 0 1 2 2v9M5 8v9a2 2 0 0 0 2 2h9" {...LINE} />;
  }
}

/** Drawn 24-unit glyph for wellbeing levels and the tab's few UI icons. */
export function WellbeingIcon({ kind, size = 20 }: { kind: WellbeingGlyph; size?: number }) {
  return (
    <svg className="state-icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {glyph(kind)}
    </svg>
  );
}

/** Chevron / arrow strokes shared by buttons and the trend mark. */
export function Arrow({ d, size = 18 }: { d: string; size?: number }) {
  return (
    <svg className="state-icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d={d} {...LINE} />
    </svg>
  );
}

export const CHEVRON = {
  down: "M6 9l6 6 6-6",
  up: "M6 15l6-6 6 6",
  left: "M15 18l-6-6 6-6",
} as const;

interface PillProps {
  level: SupportLevel | IndicatorStatus;
  kind?: "support" | "indicator";
  size?: "sm" | "md" | "lg";
}

const ICON_SIZE = { sm: 18, md: 20, lg: 26 } as const;

export function WellbeingPill({ level, kind = "support", size = "md" }: PillProps) {
  const label =
    kind === "indicator"
      ? INDICATOR_STATUS_LABELS[level as IndicatorStatus]
      : SUPPORT_LABELS[level as SupportLevel];
  return (
    <span className={`wpill wpill--${level} wpill--${size}`}>
      <WellbeingIcon kind={level} size={ICON_SIZE[size]} />
      {label}
    </span>
  );
}

const ORIGIN_LABELS: Record<Origin, string> = { live: "LIVE", simulated: "SIMULATED", mixed: "MIXED" };

/** LIVE / SIMULATED / MIXED chip. Nothing when there is no data. */
export function OriginMark({ origin }: { origin: Origin | null }) {
  if (origin === null) return null;
  return (
    <span className={`origin origin--${origin}`}>
      {origin !== "simulated" && (
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          {origin === "live" ? (
            <circle cx="5" cy="5" r="4" fill="currentColor" />
          ) : (
            <>
              <circle cx="5" cy="5" r="4" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5 1a4 4 0 0 1 0 8z" fill="currentColor" />
            </>
          )}
        </svg>
      )}
      {ORIGIN_LABELS[origin]}
    </span>
  );
}

const TREND_PATHS: Record<Exclude<Trend, "unknown">, string> = {
  improving: "M7 17L17 7M9 7h8v8",
  stable: "M5 12h14M13 6l6 6-6 6",
  worsening: "M7 7l10 10M17 9v8H9",
};

export function TrendMark({ trend }: { trend: Trend }) {
  if (trend === "unknown") {
    return (
      <span className="trend">
        <span aria-hidden="true">{TREND_LABELS.unknown}</span>
        <span className="sr-only">Trend unknown</span>
      </span>
    );
  }
  return (
    <span className="trend">
      <Arrow d={TREND_PATHS[trend]} />
      {TREND_LABELS[trend]}
    </span>
  );
}

const CONFIDENCE_BARS: Record<Confidence, number> = { low: 1, medium: 2, high: 3 };

export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  const filled = CONFIDENCE_BARS[confidence];
  return (
    <span className="confidence">
      <span className="confidence__bars" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={i <= filled ? "confidence__bar confidence__bar--on" : "confidence__bar"} />
        ))}
      </span>
      {CONFIDENCE_LABELS[confidence]}
    </span>
  );
}
