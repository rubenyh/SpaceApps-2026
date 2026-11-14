import type { AstronautStatus, ReadingStatus, SensorKind, SensorStatus } from "../api/types";

export function findSensor(
  status: AstronautStatus | null | undefined,
  kind: SensorKind,
): SensorStatus | null {
  return status?.sensors.find((s) => s.kind === kind) ?? null;
}

/**
 * Age that keeps ticking between polls: the service's `age_seconds` (as of the
 * response) plus the time elapsed since the response arrived.
 */
export function liveAge(
  sensor: SensorStatus | null,
  updatedAt: number | null,
  now: number,
): number | null {
  if (!sensor || sensor.age_seconds === null) return null;
  const elapsed = updatedAt === null ? 0 : Math.max(0, (now - updatedAt) / 1000);
  return sensor.age_seconds + elapsed;
}

/** Border/inverse treatment class for a state box. */
export function stateBoxClass(status: ReadingStatus | "doubtful"): string {
  return `statebox statebox--${status}`;
}

export const URINE_KINDS: SensorKind[] = [
  "urine_ph",
  "urine_salinity",
  "urine_color",
  "urine_temperature",
];

const URINE_RANK: Record<ReadingStatus, number> = {
  alert: 4,
  stale: 3,
  normal: 2,
  no_range: 1,
  no_data: 0,
};

/**
 * Most relevant status across the urine measurements (radiation excluded).
 * Precedence: alert > stale > normal > no_range > no_data, so a missing
 * measurement never hides a present one (missing ones are listed separately).
 * A urine temperature "alert" is about sample validity, not health, so it
 * never raises the aggregate to alert.
 */
export function aggregateUrine(sensors: (SensorStatus | null)[]): ReadingStatus {
  let best: ReadingStatus = "no_data";
  for (const s of sensors) {
    if (!s) continue;
    let st = s.status;
    if (st === "alert" && s.config.range_role === "sample_validity") st = "normal";
    if (URINE_RANK[st] > URINE_RANK[best]) best = st;
  }
  return best;
}
