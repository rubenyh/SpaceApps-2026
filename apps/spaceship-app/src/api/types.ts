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

/**
 * No clinician is on board and the ground link may be down. immediate: emergency,
 * act now with the steps and the mission emergency procedure. review_required: act
 * with the steps and keep monitoring. undetermined: a decisive datum is missing.
 * informational: general information only.
 */
export type Urgency = "immediate" | "review_required" | "undetermined" | "informational";
export type SymptomStatus = "present" | "absent" | "unknown";
export type CandidateStatus = "compatible" | "rule_out" | "insufficient_evidence";

/**
 * Closed vocabulary shared by structured input, text interpretation and rules.
 * Some codes are context, not symptoms (heat_exposure, intense_exertion,
 * allergen_exposure, multiple_crew_symptoms, *_reported alerts).
 */
export const SYMPTOM_CODES = [
  "shortness_of_breath",
  "abnormal_breathing",
  "chest_pain",
  "cold_sweat",
  "palpitations",
  "speech_change",
  "facial_droop",
  "one_sided_weakness",
  "vision_loss",
  "sudden_severe_headache",
  "headache",
  "unresponsive",
  "fainting",
  "seizure",
  "throat_swelling",
  "hives",
  "allergen_exposure",
  "fever",
  "chills",
  "cough",
  "malaise",
  "confusion",
  "stiff_neck",
  "dizziness",
  "nausea",
  "vomiting",
  "diarrhea",
  "low_fluid_intake",
  "unable_to_keep_fluids",
  "low_urine_output",
  "vomiting_blood",
  "abdominal_pain",
  "black_stool",
  "blood_in_stool",
  "heat_exposure",
  "heavy_sweating",
  "collapse",
  "urinary_burning",
  "urinary_urgency",
  "flank_pain",
  "visible_blood_in_urine",
  "unable_to_urinate",
  "muscle_pain",
  "muscle_cramps",
  "muscle_weakness",
  "dark_urine",
  "intense_exertion",
  "injury",
  "head_injury",
  "bleeding",
  "heavy_bleeding",
  "burn",
  "severe_burn",
  "repeated_vomiting",
  "multiple_crew_symptoms",
  "cabin_alarm_reported",
  "radiation_alert_reported",
] as const;

export type SymptomCode = (typeof SYMPTOM_CODES)[number];

/** One structured observation. Overrides text interpretation of the same code. */
export interface ReportedSymptom {
  symptom: SymptomCode;
  /** Default "present". */
  status?: SymptomStatus;
  onset?: "sudden" | "gradual" | null;
  severity?: "mild" | "moderate" | "severe" | null;
  persistence?: "ongoing" | "resolved" | "recurrent" | null;
  /** With UTC offset. */
  started_at?: string | null;
  /** Max 200 chars. */
  context?: string | null;
}

export interface AssistantRequest {
  /** 1 to 4000 chars. */
  message: string;
  /** Person being assessed. */
  astronaut_id?: string | null;
  /** Crewmate who sends the report, when it is not the assessed person. */
  reported_by?: string | null;
  /** Max 40. Overrides text interpretation of the same code. */
  reported_symptoms?: ReportedSymptom[];
  /** `clarification` from the previous response, echoed unchanged; `message` then holds only the answer. */
  clarification?: Clarification | null;
}

/** One observation of an open case, returned by the server and echoed back unchanged. */
export interface CaseObservation {
  symptom: SymptomCode;
  status: SymptomStatus;
  origin: "structured" | "text" | "llm";
  evidence: string;
  temporality?: "current" | "resolved" | "historical" | "hypothetical";
  subject?: "self" | "other";
  onset?: "sudden" | "gradual" | null;
  severity?: "mild" | "moderate" | "severe" | null;
  persistence?: "ongoing" | "resolved" | "recurrent" | null;
  context?: string | null;
}

/** Open case with a pending question. The endpoint keeps no conversation: send it back unchanged. */
export interface Clarification {
  /** "routing", "symptom" or "<protocol_id>.<question_key>". */
  question_id: string;
  question: string;
  /** The case belongs to this person; another astronaut_id starts a new case. */
  astronaut_id: string | null;
  observations: CaseObservation[];
}

/** A protocol card (kind="protocol") or a retrieved corpus chunk (kind="guide"). */
export interface GuideSource {
  id: string;
  title: string;
  section: string | null;
  url: string | null;
  kind: "protocol" | "guide";
}

export interface MatchedRule {
  rule_id: string;
  protocol_id: string;
  protocol_version: string;
  urgency: Urgency;
}

export interface Finding {
  kind: "symptom" | "reading" | "event" | "data_gap";
  detail: string;
  /** "report" (text), "structured", "sqlite:<kind>", "event:<id>". */
  source: string;
  /** Evidence quality. Optional for older servers. */
  evidence_flags?: EvidenceFlag[];
}

export type EvidenceFlag = "simulated" | "stale" | "missing" | "poor_quality";

/** Onboard incident stored for an `immediate` response. */
export interface IncidentRef {
  id: string | null;
  recorded: boolean;
  /** Why nothing was stored, when recorded is false. */
  error: string | null;
}

/** Candidate from the protocol's reviewed catalog. Never a probability. */
export interface PossibleCause {
  id: string;
  label: string;
  status: CandidateStatus;
  evidence_for: string[];
  missing_data: string[];
  source_ids: string[];
}

/** One cited checklist step. self: one awake astronaut alone; crew: needs another crew member; equipment: needs a device or kit. */
export interface ActionStep {
  text: string;
  who: "self" | "crew" | "equipment";
  /** GuideSource ids in `sources`. */
  source_ids: string[];
}

/** Mission procedure an action points to. loaded=false: its text is not in the assistant. */
export interface MissionProcedure {
  title: string;
  loaded: boolean;
}

/** Deterministic case report to copy. Nothing transmits it. */
export interface CaseReport {
  text: string;
  transmission: "not_sent";
}

/** Same shape for every workflow. New workflows add a `workflow` value. */
export interface AssistantResponse {
  reply: string;
  workflow: AssistantWorkflow;
  needs_clarification: boolean;
  sources: GuideSource[];
  data_notices: string[];
  disclaimer: string | null;
  urgency: Urgency | null;
  action: string | null;
  /** Who to tell, e.g. "tripulación". Nothing is transmitted. */
  notify: string[];
  /** Cited checklist of the action, in order. Optional for older servers. */
  steps?: ActionStep[];
  mission_procedures?: MissionProcedure[];
  /** Guidance the cards cannot give, stated explicitly. */
  missing_guidance?: string[];
  report?: CaseReport | null;
  protocol_id: string | null;
  additional_protocol_ids: string[];
  matched_rules: MatchedRule[];
  findings: Finding[];
  possible_causes: PossibleCause[];
  clarifying_question: string | null;
  /** Set with needs_clarification on medical/clarify replies: send it back unchanged. */
  clarification: Clarification | null;
  /** Set only when urgency is "immediate". Optional for older servers. */
  incident?: IncidentRef | null;
}
