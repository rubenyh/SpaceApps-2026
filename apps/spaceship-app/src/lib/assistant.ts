import type {
  AssistantRequest,
  CandidateStatus,
  ReportedSymptom,
  SymptomCode,
  SymptomStatus,
  Urgency,
} from "../api/types";

/** English translation of LABELS in the onboard medical triage (the service itself answers in Spanish). */
export const SYMPTOM_LABELS: Record<SymptomCode, string> = {
  shortness_of_breath: "Shortness of breath",
  abnormal_breathing: "Abnormal breathing",
  chest_pain: "Chest pain or pressure",
  cold_sweat: "Cold sweat",
  palpitations: "Palpitations",
  speech_change: "Speech change",
  facial_droop: "Facial droop",
  one_sided_weakness: "Weakness on one side",
  vision_loss: "Vision loss",
  sudden_severe_headache: "Sudden severe headache",
  headache: "Headache",
  unresponsive: "Unresponsive",
  fainting: "Fainting or loss of consciousness",
  seizure: "Seizure",
  throat_swelling: "Throat or tongue swelling",
  hives: "Hives",
  allergen_exposure: "Possible allergen exposure",
  fever: "Fever",
  chills: "Chills",
  cough: "Cough",
  malaise: "General malaise",
  confusion: "Confusion",
  stiff_neck: "Stiff neck",
  dizziness: "Dizziness",
  nausea: "Nausea",
  vomiting: "Vomiting",
  diarrhea: "Diarrhea",
  low_fluid_intake: "Low fluid intake",
  unable_to_keep_fluids: "Cannot keep fluids down",
  low_urine_output: "Low urine output",
  vomiting_blood: "Vomiting blood",
  abdominal_pain: "Abdominal pain",
  black_stool: "Black stool",
  blood_in_stool: "Blood in stool",
  heat_exposure: "Heat exposure",
  heavy_sweating: "Heavy sweating",
  collapse: "Collapse",
  urinary_burning: "Burning when urinating",
  urinary_urgency: "Urinary urgency",
  flank_pain: "Flank pain",
  visible_blood_in_urine: "Visible blood in urine",
  unable_to_urinate: "Unable to urinate",
  muscle_pain: "Muscle pain",
  muscle_cramps: "Cramps",
  muscle_weakness: "Muscle weakness",
  dark_urine: "Tea- or cola-colored urine reported",
  intense_exertion: "Physical exertion",
  injury: "Blow or injury",
  head_injury: "Head injury",
  bleeding: "Bleeding",
  heavy_bleeding: "Heavy bleeding that continues",
  burn: "Burn",
  severe_burn: "Severe burn",
  repeated_vomiting: "Repeated vomiting",
  multiple_crew_symptoms: "Several crew members with symptoms at once",
  cabin_alarm_reported: "Cabin alarm",
  radiation_alert_reported: "Radiation alert",
};

export const SYMPTOM_STATUS_LABELS: Record<SymptomStatus, string> = {
  present: "Yes",
  absent: "No",
  unknown: "Unknown",
};

export const URGENCY_LABELS: Record<Urgency, string> = {
  immediate: "Immediate onboard alert",
  review_required: "Ask the crew medical officer for an assessment",
  undetermined: "A decisive piece of data is missing",
  informational: "General information",
};

export const CAUSE_STATUS_LABELS: Record<CandidateStatus, string> = {
  compatible: "Consistent with the report",
  rule_out: "Needs to be ruled out",
  insufficient_evidence: "Insufficient evidence",
};

const MAX_MESSAGE = 4000;
const MAX_SYMPTOMS = 40;

/** Adds or replaces observations by code: the newest answer about a symptom wins. */
export function mergeSymptoms(prev: ReportedSymptom[], added: ReportedSymptom[]): ReportedSymptom[] {
  const codes = new Set(added.map((s) => s.symptom));
  return [...prev.filter((s) => !codes.has(s.symptom)), ...added].slice(-MAX_SYMPTOMS);
}

/**
 * The endpoint is stateless. Answering a clarifying question keeps the case's people and
 * symptoms. With a server `clarification` it is echoed and `message` is only the answer;
 * without one the original message is resent with the answer appended.
 */
export function buildRequest(
  pending: AssistantRequest | null,
  text: string,
  astronautId: string | null,
  reportedBy: string | null,
  symptoms: ReportedSymptom[],
): AssistantRequest {
  if (!pending) {
    return { message: text, astronaut_id: astronautId, reported_by: reportedBy, reported_symptoms: symptoms };
  }
  const base = {
    astronaut_id: pending.astronaut_id,
    reported_by: pending.reported_by,
    reported_symptoms: mergeSymptoms(pending.reported_symptoms ?? [], symptoms),
  };
  if (pending.clarification) {
    return { message: text.slice(0, MAX_MESSAGE), ...base, clarification: pending.clarification };
  }
  return { message: `${pending.message}\n${text}`.slice(0, MAX_MESSAGE), ...base };
}
