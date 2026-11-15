import type { ReadingStatus } from "../api/types";

/** Reading status plus "doubtful" (sample validity out of range: not a health alert). */
export type VisualState = ReadingStatus | "doubtful";

export const STATE_LABELS: Record<VisualState, string> = {
  alert: "Alert",
  normal: "Normal",
  stale: "Old data",
  no_data: "No data",
  no_range: "No range",
  doubtful: "Doubtful sample",
};

const LINE = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" } as const;

function shape(state: VisualState) {
  switch (state) {
    case "alert":
      // The "!" is cut out with the colour behind the icon (--icon-cut).
      return (
        <>
          <path d="M8 1.2 L15.2 14.4 H0.8 Z" fill="currentColor" />
          <rect className="state-icon__cut" x="7.1" y="5.4" width="1.8" height="4.8" />
          <rect className="state-icon__cut" x="7.1" y="11.3" width="1.8" height="1.8" />
        </>
      );
    case "normal":
      return (
        <>
          <circle cx="8" cy="8" r="6.6" {...LINE} />
          <path d="M4.8 8.2 L7.1 10.4 L11.3 5.9" {...LINE} strokeLinejoin="round" />
        </>
      );
    case "stale":
      return (
        <>
          <circle cx="8" cy="8" r="6.6" {...LINE} />
          <path d="M8 4.2 V8 L10.8 9.8" {...LINE} />
        </>
      );
    case "no_data":
      return (
        <>
          <circle cx="8" cy="8" r="6.6" {...LINE} strokeWidth={1.6} strokeDasharray="2.4 2.2" />
          <path d="M4.6 8 H11.4" {...LINE} />
        </>
      );
    case "no_range":
      return <path d="M8 1.6 L14.4 8 L8 14.4 L1.6 8 Z" {...LINE} strokeLinejoin="round" />;
    case "doubtful":
      return (
        <>
          <circle cx="8" cy="8" r="6.6" {...LINE} />
          <path d="M6 6.2 C6 5 6.9 4.2 8 4.2 C9.2 4.2 10 5 10 6 C10 7.4 8 7.4 8 9" {...LINE} />
          <rect x="7.2" y="10.6" width="1.6" height="1.6" fill="currentColor" />
        </>
      );
  }
}

interface IconProps {
  state: VisualState;
  size?: number;
  /** Pulse when the state is alert (off under prefers-reduced-motion). */
  pulse?: boolean;
}

/** State glyph. Each state has its own shape, so it reads without colour. */
export function StateIcon({ state, size = 16, pulse = false }: IconProps) {
  const cls = `state-icon${pulse && state === "alert" ? " alert-pulse" : ""}`;
  return (
    <svg className={cls} width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
      {shape(state)}
    </svg>
  );
}

/** State label: icon + text + border style per state. */
export function StatusPill({ state }: { state: VisualState }) {
  return (
    <span className={`pill pill--${state}`}>
      <StateIcon state={state} pulse />
      {STATE_LABELS[state]}
    </span>
  );
}
