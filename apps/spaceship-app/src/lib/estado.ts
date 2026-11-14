import type { AstronautStatus, ReadingStatus, SensorKind, SensorStatus } from "../api/types";

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

/** Status to draw: while the service is unreachable, known values are shown as stale. */
export function shownStatus(s: SensorStatus | null, offline: boolean): ReadingStatus {
  const st = s?.status ?? "no_data";
  return offline && st !== "no_data" ? "stale" : st;
}

/** One-line plain explanation under the value. */
export function explain(s: SensorStatus | null, offline: boolean): string {
  const st = s?.status ?? "no_data";
  if (!s || st === "no_data") return "Todavía no hay lecturas";
  if (st === "stale") return "Dato antiguo: puede haber cambiado";
  const side = rangeSide(s);
  if (offline) {
    if (st === "alert" && side === "high") return "Último valor recibido: estaba alto";
    if (st === "alert" && side === "low") return "Último valor recibido: estaba bajo";
    if (st === "normal") return "Último valor recibido: estaba normal";
    return "Último valor recibido";
  }
  if (st === "no_range") return "Sin rango de referencia";
  if (st === "alert") {
    if (side === "high") return "Por encima de lo normal";
    if (side === "low") return "Por debajo de lo normal";
    return "Fuera de lo normal";
  }
  return "Dentro de lo normal";
}
