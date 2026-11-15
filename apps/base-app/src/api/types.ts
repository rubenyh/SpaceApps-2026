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

// --- Incidents (incident contract section 7, ground GET /incidents) -----------

export type IncidentUpdateType = "created" | "acknowledged" | "closed";

export interface GroundMatchedRule {
  rule_id: string;
  protocol_id: string | null;
  protocol_version: string | null;
}

export interface GroundAcknowledgment {
  acknowledged_by: string;
  /** Onboard event time (occurred_at of the acknowledged update). */
  acknowledged_at: string;
  /** Ground clock. */
  received_at: string;
}

export interface GroundIncidentUpdate {
  id: string;
  type: IncidentUpdateType;
  /** Original onboard event time. */
  occurred_at: string;
  /** Ground clock when the update was stored. */
  received_at: string;
  acknowledged_by: string | null;
}

/** GET /incidents item (newest began_at first) and GET /incidents/{id}. */
export interface GroundIncident {
  ship_id: string;
  id: string;
  astronaut_id: string | null;
  /** null until the "created" update arrives. */
  began_at: string | null;
  urgency: string;
  protocol_id: string | null;
  protocol_version: string | null;
  matched_rules: GroundMatchedRule[];
  action: string | null;
  acknowledgments: GroundAcknowledgment[];
  /** Sorted by occurred_at asc. */
  updates: GroundIncidentUpdate[];
  /** Optional: absent on incidents stored before issue #67. */
  reported_via?: "console" | "watch" | null;
  /** Onboard readings snapshot taken at creation, joined on ground. */
  readings?: GroundReading[];
  /** Snapshot readings not yet received by ground. */
  missing_reading_ids?: number;
  /** Case reports linked to this incident. Absent on older servers: treat as []. */
  report_ids?: string[];
}

// --- Case reports (contracts/case-report/README.md, ground GET /case-reports) --

export type CaseUrgency = "immediate" | "review_required" | "undetermined" | "informational";

/** Reading as captured onboard for the report, with provenance and freshness at assessment time. */
export interface SnapshotReading {
  id: number;
  kind: string;
  value: number | null;
  value_text: string | null;
  unit: string;
  recorded_at: string;
  received_at: string;
  quality: Quality;
  source: string;
  simulated: boolean;
  freshness: "current" | "stale" | "future";
  age_seconds: number;
}

/** GET /case-reports item (newest received_at first) and GET /case-reports/{report_id}. */
export interface GroundCaseReport {
  schema_version: 1;
  report_id: string;
  ship_id: string;
  astronaut_id: string | null;
  reported_by: string | null;
  sent_by: string | null;
  urgency: CaseUrgency;
  protocol_id: string | null;
  action: string | null;
  /** Onboard clock when the readings were loaded. */
  assessed_at: string;
  created_at: string;
  sent_at: string;
  incident_id: string | null;
  text: string;
  readings: SnapshotReading[];
  knowledge_version: CandidateRef | null;
  /** Ground clock when the report was stored. */
  received_at: string;
}

// --- Medical evaluation (contracts/medical-eval/README.md, sections 1-4) ------

export type CandidateStatus = "pending_review" | "approved" | "rejected";
export type ReviewRole = "clinician" | "simulated";
export type DecisionKind = "approved" | "rejected";
export type FindingKind = "possible_cause" | "warning_sign" | "question" | "action";

export interface CandidateRef {
  candidate_id: string;
  digest: string;
}

export interface ManifestComponent {
  kind: string;
  path: string;
  sha256: string;
  value?: unknown;
}

/** Section 2. */
export interface EvalManifest extends CandidateRef {
  schema: string;
  created_at: string;
  components: ManifestComponent[];
}

export interface EvalSummary {
  cases: number;
  passed: number;
  failed: number;
  blocking_failures: number;
  release_blocked: boolean;
  retrieval_hit_rate: number;
  citation_support_rate: number;
  latency_ms_p50: number;
  latency_ms_p95: number;
}

/** Onboard GuideSource; fields other than id may be null. */
export interface EvalSource {
  id: string;
  title: string | null;
  section: string | null;
  url: string | null;
  kind: "protocol" | "guide" | null;
}

/** Section 1 case. Only the fields the console reads are typed precisely. */
export interface EvalCase {
  case_id: string;
  version: number;
  family: string;
  tags: string[];
  turns: unknown[];
  readings: unknown[];
  events: unknown[];
  dependencies: Record<string, "up" | "down">;
  expected: {
    workflow: string;
    urgency: string | null;
    protocol_id: string | null;
    clarify: boolean;
    required_actions: string[];
    prohibited_actions: string[];
    acceptable_sources: string[];
  };
  review: { status: string; reviewer: string | null; reviewed_at: string | null; notes: string };
}

export interface EvalResponse {
  workflow: string;
  urgency: string | null;
  protocol_id: string | null;
  reply: string;
  action: string | null;
  sources: EvalSource[];
}

export interface EvalCaseResult {
  case_id: string;
  family: string;
  review_status: string;
  passed: boolean;
  blocking: boolean;
  failures: { code: string; detail: string }[];
  latency_ms: number;
  response: EvalResponse | null;
  baseline_response: EvalResponse | null;
  case: EvalCase;
}

/** Section 3. */
export interface EvalResult {
  schema: string;
  manifest: CandidateRef;
  baseline: CandidateRef | null;
  run_at: string;
  summary: EvalSummary;
  cases: EvalCaseResult[];
}

/** POST /medical-eval/candidates/{digest}/decisions body. */
export interface DecisionBody {
  decision: DecisionKind;
  reviewer: string;
  role: ReviewRole;
  notes: string;
}

export interface DecisionRecord extends DecisionBody {
  digest: string;
  decided_at: string;
}

export interface FindingBody {
  case_id: string;
  kind: FindingKind;
  when_it_applies: string;
  source: string;
  expected_behavior: string;
  reporter: string;
}

export interface EvalFinding extends FindingBody {
  id: string;
  digest: string;
  created_at: string;
  status: string;
}

/** GET /medical-eval/candidates item. */
export interface CandidateListItem extends CandidateRef {
  status: CandidateStatus;
  created_at: string;
  summary: EvalSummary;
  decision: DecisionRecord | null;
}

/** GET /medical-eval/candidates/{digest}. */
export interface CandidateDetail {
  manifest: EvalManifest;
  result: EvalResult;
  status: CandidateStatus;
  decisions: DecisionRecord[];
  findings: EvalFinding[];
}
