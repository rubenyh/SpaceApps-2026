// Ground read API contract (contracts/telemetry/README.md, "Ground read API").
// Mirrors services/ground-api/src/ground_api/schemas.py field by field.
// All timestamps are ISO 8601 UTC strings.

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

export interface SensorConfig {
  kind: SensorKind;
  /** null: unit not defined yet. */
  unit: string | null;
  /** null: readings of this kind never become "stale". */
  stale_after_seconds: number | null;
  /** Both null: no reference range, status is "no_range". */
  normal_min: number | null;
  normal_max: number | null;
  range_role: RangeRole;
  provisional: boolean;
  range_source: string | null;
}

/** Onboard Reading plus the time ground stored it. */
export interface GroundReading {
  /** Onboard reading id. */
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
  ground_received_at: string;
}

/** Status computed by ground with its own clock: link delay counts toward staleness. */
export interface SensorStatus {
  kind: SensorKind;
  status: ReadingStatus;
  latest: GroundReading | null;
  age_seconds: number | null;
  config: SensorConfig;
}

/** GET /crew item. Sensors in SENSOR_KINDS order. */
export interface CrewMember {
  astronaut_id: string;
  display_name: string;
  sensors: SensorStatus[];
}

/** GET /link. Nulls before the first batch. */
export interface Link {
  ship_id: string | null;
  last_batch_sent_at: string | null;
  last_batch_received_at: string | null;
  seconds_since_last_batch: number | null;
  batches_received: number;
  readings_received: number;
}

/** GET /alerts item: a reading that was outside its health range when it arrived. */
export interface Alert {
  reading: GroundReading;
  normal_min: number | null;
  normal_max: number | null;
  side: "high" | "low";
}
