// Shared API contract between onboard-api and the astronaut console.
//
// Mirrors services/onboard-api/src/onboard_api/schemas/ field by field.
// Change both together, and only after the main session agrees.
//
// Datetimes are ISO 8601 strings in UTC.

export const SENSOR_KINDS = [
  "heart_rate",
  "spo2",
  "muscle_density",
  "urine_ph",
  "urine_salinity",
  "urine_color",
  "urine_temperature",
  "urine_radiation_marker",
] as const;

export type SensorKind = (typeof SENSOR_KINDS)[number];
export type Quality = "good" | "suspect" | "bad";
export type ReadingStatus = "normal" | "alert" | "no_data" | "stale" | "no_range";
export type RangeRole = "health" | "sample_validity";
export type AssistantWorkflow = "medical" | "clarify" | "unsupported";

/** Body of 404 and 409 responses. */
export interface ErrorResponse {
  detail: string;
}

// --- Astronauts ---

export interface AstronautCreate {
  /** Slug matching ^[a-z0-9][a-z0-9-]{1,31}$ */
  id: string;
  display_name: string;
}

export interface Astronaut {
  id: string;
  display_name: string;
  created_at: string;
}

// --- Sensor configuration ---

export interface SensorConfigUpdate {
  /** null: unit not defined yet, readings may carry any unit. */
  unit: string | null;
  /** null: readings of this kind never become "stale". */
  stale_after_seconds: number | null;
  /** Both null: no reference range, status is "no_range". */
  normal_min: number | null;
  normal_max: number | null;
  /** "sample_validity": the range says whether the sample is usable, not a health range. */
  range_role: RangeRole;
  provisional: boolean;
  range_source: string | null;
}

export interface SensorConfig extends SensorConfigUpdate {
  kind: SensorKind;
}

// --- Readings ---

export interface ReadingCreate {
  astronaut_id: string;
  kind: SensorKind;
  /** Exactly one of value / value_text is set. */
  value?: number | null;
  /** Non-numeric readings. urine_color is "#RRGGBB". */
  value_text?: string | null;
  unit: string;
  /** Capture time, with UTC offset. */
  recorded_at: string;
  quality: Quality;
  /** e.g. "manual" or "serial:pulse". */
  source: string;
}

export interface Reading {
  id: number;
  astronaut_id: string;
  kind: SensorKind;
  value: number | null;
  value_text: string | null;
  unit: string;
  recorded_at: string;
  received_at: string;
  quality: Quality;
  source: string;
}

/** Query of GET /readings. */
export interface ReadingsQuery {
  astronaut_id: string;
  kind?: SensorKind;
  since?: string;
  until?: string;
  /** Default 100, max 1000. */
  limit?: number;
}

// --- Status ---

/**
 * Status precedence (computed by the service):
 *   1. no reading at all                -> "no_data"
 *   2. older than stale_after_seconds   -> "stale" (value shown, not evaluated)
 *   3. no range, or a value_text value  -> "no_range"
 *   4. outside [normal_min, normal_max] -> "alert", otherwise "normal"
 */
export interface SensorStatus {
  kind: SensorKind;
  status: ReadingStatus;
  latest: Reading | null;
  age_seconds: number | null;
  config: SensorConfig;
}

export interface AstronautStatus {
  astronaut_id: string;
  generated_at: string;
  /** Always one entry per SensorKind, in SENSOR_KINDS order. */
  sensors: SensorStatus[];
}

// --- Assistant ---

export interface GuideSource {
  id: string;
  title: string;
}

export interface AssistantRequest {
  message: string;
  astronaut_id?: string | null;
}

export interface AssistantResponse {
  reply: string;
  workflow: AssistantWorkflow;
  needs_clarification: boolean;
  sources: GuideSource[];
  data_notices: string[];
  disclaimer: string | null;
}
