import type { Quality, Reading, ReadingStatus, SensorConfig, SensorKind } from "../api/types";

export const SENSOR_LABELS: Record<SensorKind, string> = {
  heart_rate: "PULSO",
  spo2: "SpO₂",
  muscle_density: "DENSIDAD MUSCULAR",
  urine_ph: "ORINA·pH",
  urine_salinity: "ORINA·SALINIDAD",
  urine_color: "ORINA·COLOR",
  urine_temperature: "ORINA·TEMPERATURA",
  urine_radiation_marker: "ORINA·MARCADOR RADIACIÓN",
};

export const STATUS_MARKERS: Record<ReadingStatus, string> = {
  normal: "[ OK ]",
  alert: "[!! ALERTA ]",
  no_data: "[-- SIN DATOS ]",
  stale: "[~ VIEJO ]",
  no_range: "[? SIN RANGO ]",
};

export const QUALITY_LABELS: Record<Quality, string> = {
  good: "BUENA",
  suspect: "DUDOSA ?",
  bad: "MALA ✕",
};

/** Display label for a unit coming from the API. Only `bpm` is relabelled. */
export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return "";
  if (unit === "bpm") return "lpm";
  return unit;
}

/** Round to at most `maxDecimals` without padding zeros. */
export function formatNumber(value: number, maxDecimals = 2): string {
  if (!Number.isFinite(value)) return "---";
  if (Number.isInteger(value)) return String(value);
  const factor = 10 ** maxDecimals;
  return String(Math.round(value * factor) / factor);
}

/** Signed number, e.g. "+1.2" / "−3.1" (true minus sign). */
export function formatSigned(value: number, maxDecimals = 2): string {
  const abs = formatNumber(Math.abs(value), maxDecimals);
  if (abs === "0") return "0";
  return value < 0 ? `−${abs}` : `+${abs}`;
}

/** Value of a reading as text, without unit. Never invents a value. */
export function readingValueText(reading: Reading | null | undefined): string {
  if (!reading) return "---";
  if (reading.value_text !== null && reading.value_text !== undefined) return reading.value_text;
  if (reading.value !== null && reading.value !== undefined) return formatNumber(reading.value);
  return "---";
}

/** Relative age in Spanish: «hace 12 s», «hace 3 min», «hace 26 h», «hace 2 d». */
export function formatAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  if (seconds < 0) return "fecha futura";
  const s = Math.floor(seconds);
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 48 * 3600) return `hace ${Math.floor(s / 3600)} h`;
  return `hace ${Math.floor(s / 86400)} d`;
}

export function ageSecondsFrom(iso: string, nowMs: number = Date.now()): number | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return (nowMs - t) / 1000;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** "2026-11-14 18:02:11" in UTC. */
export function formatUtcDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
  );
}

export function formatUtcClock(d: Date): string {
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`
  );
}

/** "11-14" in UTC. */
export function formatUtcDay(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** "18:02" in UTC. */
export function formatUtcTime(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** Range text for a config, or null when the range is not defined. */
export function rangeText(config: SensorConfig): string | null {
  const { normal_min: min, normal_max: max } = config;
  if (min === null && max === null) return null;
  const unit = unitLabel(config.unit);
  const suffix = unit ? ` ${unit}` : "";
  if (min !== null && max !== null) return `${formatNumber(min)}–${formatNumber(max)}${suffix}`;
  if (min !== null) return `≥ ${formatNumber(min)}${suffix}`;
  return `≤ ${formatNumber(max as number)}${suffix}`;
}

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

export function isHexColor(value: string | null | undefined): value is string {
  return typeof value === "string" && HEX_COLOR.test(value);
}

/** Readings sorted oldest first (API returns newest first). */
export function chronological(readings: Reading[]): Reading[] {
  return [...readings].sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at));
}
