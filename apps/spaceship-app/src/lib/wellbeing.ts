// Labels and small pure helpers for the Wellbeing tab (docs/design/wellbeing/HANDOFF.md).
import type {
  Confidence,
  CrewMemberSummary,
  IndicatorKind,
  IndicatorStatus,
  SupportLevel,
  Trend,
  WellbeingAssessment,
  WellbeingSource,
} from "../api/types";

export const SUPPORT_LABELS: Record<SupportLevel, string> = {
  ok: "Doing well",
  attention: "Attention",
  needs_support: "Needs support",
  baseline_pending: "Calibrating",
  stale: "No recent data",
  no_data: "No data",
};

/** Same map as SupportLevel, worded for one indicator. */
export const INDICATOR_STATUS_LABELS: Record<IndicatorStatus, string> = {
  ok: "Within usual",
  attention: "Changed vs. usual",
  baseline_pending: "Calibrating",
  stale: "Old data",
  no_data: "No data",
};

export const INDICATOR_LABELS: Record<IndicatorKind, string> = {
  sleep: "Sleep",
  fatigue: "Fatigue",
  stress: "Stress",
  activation: "Activation",
  social: "Social",
  mood: "Mood",
};

export const SOURCE_LABELS: Record<WellbeingSource, string> = {
  checkin: "Check-in",
  vision: "Vision",
  physiology: "Physiology",
  social: "Social",
};

export const TREND_LABELS: Record<Trend, string> = {
  improving: "Improving",
  stable: "Stable",
  worsening: "Worsening",
  unknown: "—",
};

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

/** Timeline length. The demo history has 21 days; 30 would show 9 empty columns. */
export const TIMELINE_DAYS = 21;

/** ZTrack scale (adverse z: positive = further from the person's usual). */
export const Z_MIN = -2;
export const Z_MAX = 4;

export const sourcesText = (sources: WellbeingSource[]) =>
  sources.length > 0 ? sources.map((s) => SOURCE_LABELS[s]).join(" · ") : "---";

/** "+2.4", "−0.2" (true minus sign), "---" when missing. */
export function formatZ(z: number | null): string {
  if (z === null) return "---";
  const text = Math.abs(z).toFixed(1);
  if (text === "0.0") return "0.0";
  return `${z < 0 ? "−" : "+"}${text}`;
}

/** Position of z on the [min, max] track, clamped, in percent. */
export function zPercent(z: number, min = Z_MIN, max = Z_MAX): number {
  const p = ((z - min) / (max - min)) * 100;
  return Math.min(100, Math.max(0, p));
}

/** Timeline bar height as a fraction of the cell: min(z, 4) / 4, never negative. */
export function barFraction(z: number): number {
  return Math.min(Math.max(z, 0), Z_MAX) / Z_MAX;
}

const DAY_FMT = { timeZone: "UTC", month: "short", day: "numeric" } as const;

/** "2026-11-07" → "Nov 7". Days are calendar dates, so format them in UTC. */
export function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-US", DAY_FMT);
}

/** "2026-11-07" → "Sat, Nov 7". */
export function formatDayLong(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-US", { ...DAY_FMT, weekday: "short" });
}

/** Today's mission day (YYYY-MM-DD) in the mission time zone from GET /wellbeing/parameters. */
export function missionDay(timeZone: string, now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(now);
}

const DAY_MS = 86_400_000;

/** Calendar arithmetic on YYYY-MM-DD: addDays("2026-11-14", -20) → "2026-10-25". */
export function addDays(day: string, n: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);
}

/** Days in an inclusive period: dayCount("2026-10-25", "2026-11-14") → 21. */
export function dayCount(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS) + 1;
}

/** Valid ground-package period: both set, from ≤ to ≤ today (ISO strings compare as dates). */
export const validPeriod = (from: string, to: string, today: string) =>
  from !== "" && to !== "" && from <= to && to <= today;

/** "HH:MM" of an ISO timestamp in the mission time zone. */
export function formatClock(iso: string, timeZone = "UTC"): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit" }).format(
    new Date(iso),
  );
}

export const firstName = (displayName: string) => displayName.trim().split(/\s+/)[0] ?? displayName;

/** "checkin.sleep_hours" → "sleep hours (check-in)": the raw key, no invented clinical names. */
export function componentLabel(component: string): string {
  const dot = component.indexOf(".");
  if (dot < 0) return component.replace(/_/g, " ");
  const prefix = component.slice(0, dot);
  return `${component.slice(dot + 1).replace(/_/g, " ")} (${prefix === "checkin" ? "check-in" : prefix})`;
}

/** Component value with its unit: "4.5 h", "3 / 4" for 0-N scales, "---" when missing. */
export function formatValue(value: number | null, unit: string): string {
  if (value === null) return "---";
  const n = String(Number(value.toFixed(2)));
  const scale = /^0-(\d+)$/.exec(unit);
  if (scale) return `${n} / ${scale[1]}`;
  return unit ? `${n} ${unit}` : n;
}

const TENSION_COMPONENTS = ["vision.brow_lower_delta", "vision.brow_lower_peak_1s"];

/**
 * Today's video log: highest z of the LIVE vision components recorded today, per group.
 * Fatigue = vision.* of `fatigue`; Tension = brow lowering of `stress`.
 * null when no live vision component has today's data; a group z is null when none of its values is.
 */
export function videoLogZ(
  assessment: WellbeingAssessment,
  today: string,
): { fatigue: number | null; tension: number | null } | null {
  const live = (kind: IndicatorKind, keep: (c: string) => boolean) =>
    (assessment.indicators.find((i) => i.kind === kind)?.components ?? []).filter(
      (c) => keep(c.component) && c.latest_origin === "live" && c.latest_day === today,
    );
  const fatigue = live("fatigue", (c) => c.startsWith("vision."));
  const tension = live("stress", (c) => TENSION_COMPONENTS.includes(c));
  if (fatigue.length === 0 && tension.length === 0) return null;
  const max = (list: typeof fatigue) => {
    const zs = list.flatMap((c) => (c.z === null ? [] : [c.z]));
    return zs.length > 0 ? Math.max(...zs) : null;
  };
  return { fatigue: max(fatigue), tension: max(tension) };
}

/** One concrete, non-judgemental gesture per crew member who may need support. */
export function supportSuggestion(member: CrewMemberSummary): { title: string; gesture: string } | null {
  const name = firstName(member.display_name);
  if (member.level === "needs_support") {
    return { title: `Check in with ${name}`, gesture: "Share a meal or ask how their week is going." };
  }
  if (member.level === "attention") {
    return { title: `Check in with ${name}`, gesture: "Invite them to the next crew activity." };
  }
  return null;
}
