import type { GroundReading, Quality, SensorConfig, SensorKind } from "../api/types";

/** Plain-text sensor names (also for <option>, where markup is not allowed). */
export const SENSOR_LABELS: Record<SensorKind, string> = {
  heart_rate: "Pulso",
  spo2: "SpO2",
  muscle_density: "Músculo",
  urine_ph: "pH orina",
  urine_salinity: "Salinidad",
  urine_color: "Color orina",
  urine_temperature: "Temp. orina",
  urine_radiation_marker: "Marcador radiación",
};

export const QUALITY_LABELS: Record<Quality, string> = {
  good: "Buena",
  suspect: "Dudosa",
  bad: "Mala",
};

/** Round to at most `maxDecimals` without padding zeros. */
export function formatNumber(value: number, maxDecimals = 2): string {
  if (!Number.isFinite(value)) return "--";
  if (Number.isInteger(value)) return String(value);
  const f = 10 ** maxDecimals;
  return String(Math.round(value * f) / f);
}

/** Value of a reading as text, without unit. Never invents a value. */
export function readingValueText(r: GroundReading | null | undefined): string {
  if (!r) return "--";
  if (r.value_text !== null && r.value_text !== undefined) return r.value_text;
  if (r.value !== null && r.value !== undefined) return formatNumber(r.value, 1);
  return "--";
}

/** "12 s", "3 min", "26 h", "3 days". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 48 * 3600) return `${Math.floor(s / 3600)} h`;
  const d = Math.floor(s / 86400);
  return `${d} ${d === 1 ? "day" : "days"}`;
}

/** "12 s ago". Empty when unknown. */
export function formatAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  if (seconds < 0) return "future date";
  return `${formatDuration(seconds)} ago`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "18:02:11" in UTC. */
export function utcSeconds(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** "18:02" in UTC. */
export function utcMinutes(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "14 nov" in UTC. */
export function utcDay(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** "14 nov 18:02:11Z" or "--" for null/invalid. */
export function utcStamp(iso: string | null | undefined): string {
  if (!iso) return "--";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return `${utcDay(t)} ${utcSeconds(t)}Z`;
}

/** Range text, or null when no range is defined. */
export function rangeText(min: number | null, max: number | null, unit: string | null): string | null {
  if (min === null && max === null) return null;
  const u = unit ? ` ${unit}` : "";
  if (min !== null && max !== null) return `${formatNumber(min)}–${formatNumber(max)}${u}`;
  if (min !== null) return `≥ ${formatNumber(min)}${u}`;
  return `≤ ${formatNumber(max as number)}${u}`;
}

export const configRange = (c: SensorConfig) => rangeText(c.normal_min, c.normal_max, c.unit);

export function isHexColor(value: string | null | undefined): value is string {
  return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value);
}
