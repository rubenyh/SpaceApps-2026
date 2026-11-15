import type { AstronautStatus, ReadingStatus, SensorKind, SensorStatus } from "../api/types";
import { URINE_KINDS, aggregateUrine, findSensor } from "./sensors.ts";

/**
 * Display axis of the range bar per sensor (from the design mockups).
 * Only where the bar starts and ends: the normal range itself comes from the service config.
 */
export const TRACK_SCALE: Partial<Record<SensorKind, [number, number]>> = {
  heart_rate: [40, 160],
  spo2: [85, 100],
  urine_ph: [4, 9],
};

/** Position of `value` on `scale` as 0–100, clamped so the marker stays on the bar. */
export function trackPercent(value: number, [lo, hi]: [number, number]): number {
  if (hi === lo) return 0;
  return Math.min(100, Math.max(0, ((value - lo) / (hi - lo)) * 100));
}

/** Side of the range the latest value is on, or null when it cannot be told. */
export function rangeSide(s: SensorStatus): "high" | "low" | "in" | null {
  const v = s.latest?.value;
  const { normal_min: min, normal_max: max } = s.config;
  if (v === null || v === undefined || (min === null && max === null)) return null;
  if (max !== null && v > max) return "high";
  if (min !== null && v < min) return "low";
  return "in";
}

/**
 * Health alerts worth the top banner, in the service's sensor order.
 * Sample-validity ranges (urine temperature) and the radiation marker are never health alerts.
 */
export function healthAlerts(status: AstronautStatus | null): SensorStatus[] {
  return (status?.sensors ?? []).filter(
    (s) =>
      s.status === "alert" &&
      s.config.range_role === "health" &&
      s.kind !== "urine_radiation_marker",
  );
}

/**
 * Status to draw: while the service is unreachable, known values are shown as stale.
 * "future" (captured ahead of the onboard clock) is kept: the clock warning still holds.
 */
export function shownStatus(s: SensorStatus | null, offline: boolean): ReadingStatus {
  const st = s?.status ?? "no_data";
  return offline && st !== "no_data" && st !== "future" ? "stale" : st;
}

/** One-line plain explanation under the value. */
export function explain(s: SensorStatus | null, offline: boolean): string {
  const st = s?.status ?? "no_data";
  if (!s || st === "no_data") return "No readings yet";
  if (st === "stale") return "Old data: it may have changed";
  if (st === "future") return "Captured ahead of the onboard clock: check the clock";
  const side = rangeSide(s);
  if (offline) {
    if (st === "alert" && side === "high") return "Last value received: it was high";
    if (st === "alert" && side === "low") return "Last value received: it was low";
    if (st === "normal") return "Last value received: it was normal";
    return "Last value received";
  }
  if (st === "no_range") return "No reference range";
  if (st === "alert") {
    if (side === "high") return "Above normal";
    if (side === "low") return "Below normal";
    return "Outside normal";
  }
  return "Within normal";
}

/** State a tab should flag: only problems (alert beats stale), never "all fine". A clock-ahead reading flags like stale. */
export type TabFlag = "alert" | "stale" | null;

function flag(statuses: ReadingStatus[]): TabFlag {
  if (statuses.includes("alert")) return "alert";
  return statuses.includes("stale") || statuses.includes("future") ? "stale" : null;
}

/** Worst state behind each detail tab. Sample-validity alerts are not health alerts. */
export function tabFlags(status: AstronautStatus | null): Record<"vitales" | "musculo" | "orina", TabFlag> {
  const of = (kind: SensorKind) => findSensor(status, kind)?.status ?? "no_data";
  return {
    vitales: flag([of("heart_rate"), of("spo2")]),
    musculo: flag([of("muscle_density")]),
    orina: flag([aggregateUrine(URINE_KINDS.map((k) => findSensor(status, k)))]),
  };
}
