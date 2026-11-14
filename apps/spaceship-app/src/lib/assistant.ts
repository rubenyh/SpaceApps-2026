import type {
  AssistantRequest,
  CandidateStatus,
  ReportedSymptom,
  SymptomCode,
  SymptomStatus,
  Urgency,
} from "../api/types";

/** Same wording as LABELS in the onboard medical triage, so chips match the findings. */
export const SYMPTOM_LABELS: Record<SymptomCode, string> = {
  shortness_of_breath: "Falta de aire",
  abnormal_breathing: "Respiración anormal",
  chest_pain: "Dolor o presión torácica",
  cold_sweat: "Sudor frío",
  palpitations: "Palpitaciones",
  speech_change: "Alteración del habla",
  facial_droop: "Asimetría facial",
  one_sided_weakness: "Debilidad de un lado",
  vision_loss: "Pérdida de visión",
  sudden_severe_headache: "Dolor de cabeza súbito e intenso",
  headache: "Dolor de cabeza",
  unresponsive: "No responde",
  fainting: "Desmayo o pérdida de conciencia",
  seizure: "Convulsión",
  throat_swelling: "Hinchazón de garganta o lengua",
  hives: "Ronchas",
  allergen_exposure: "Posible exposición a alérgeno",
  fever: "Fiebre",
  chills: "Escalofríos",
  cough: "Tos",
  malaise: "Malestar general",
  confusion: "Confusión",
  stiff_neck: "Rigidez de cuello",
  dizziness: "Mareo",
  nausea: "Náuseas",
  vomiting: "Vómitos",
  diarrhea: "Diarrea",
  low_fluid_intake: "Baja ingesta de líquidos",
  unable_to_keep_fluids: "No retiene líquidos",
  low_urine_output: "Orina escasa",
  vomiting_blood: "Vómito con sangre",
  abdominal_pain: "Dolor abdominal",
  black_stool: "Heces negras",
  blood_in_stool: "Sangre en heces",
  heat_exposure: "Exposición al calor",
  heavy_sweating: "Sudoración abundante",
  collapse: "Colapso",
  urinary_burning: "Ardor al orinar",
  urinary_urgency: "Urgencia para orinar",
  flank_pain: "Dolor de costado",
  visible_blood_in_urine: "Sangre visible en la orina",
  unable_to_urinate: "Incapacidad para orinar",
  muscle_pain: "Dolor muscular",
  muscle_cramps: "Calambres",
  muscle_weakness: "Debilidad muscular",
  dark_urine: "Orina color té o cola reportada",
  intense_exertion: "Esfuerzo físico",
  injury: "Golpe o lesión",
  head_injury: "Golpe en la cabeza",
  bleeding: "Sangrado",
  heavy_bleeding: "Sangrado abundante que continúa",
  burn: "Quemadura",
  severe_burn: "Quemadura grave",
  repeated_vomiting: "Vómitos repetidos",
  multiple_crew_symptoms: "Varios tripulantes con síntomas simultáneos",
  cabin_alarm_reported: "Alarma de cabina",
  radiation_alert_reported: "Alerta de radiación",
};

export const SYMPTOM_STATUS_LABELS: Record<SymptomStatus, string> = {
  present: "Sí",
  absent: "No",
  unknown: "No se sabe",
};

export const URGENCY_LABELS: Record<Urgency, string> = {
  immediate: "Alerta inmediata a bordo",
  review_required: "Pedir valoración al responsable médico",
  undetermined: "Falta un dato decisivo",
  informational: "Información general",
};

export const CAUSE_STATUS_LABELS: Record<CandidateStatus, string> = {
  compatible: "Compatible con lo reportado",
  rule_out: "Requiere descarte",
  insufficient_evidence: "Evidencia insuficiente",
};

const MAX_MESSAGE = 4000;
const MAX_SYMPTOMS = 40;

/** Adds or replaces observations by code: the newest answer about a symptom wins. */
export function mergeSymptoms(prev: ReportedSymptom[], added: ReportedSymptom[]): ReportedSymptom[] {
  const codes = new Set(added.map((s) => s.symptom));
  return [...prev.filter((s) => !codes.has(s.symptom)), ...added].slice(-MAX_SYMPTOMS);
}

/**
 * The endpoint is stateless: answering a clarifying question resends the original case
 * (message, astronaut_id, reported_by, symptoms) with the new text and symptoms added.
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
  return {
    message: `${pending.message}\n${text}`.slice(0, MAX_MESSAGE),
    astronaut_id: pending.astronaut_id,
    reported_by: pending.reported_by,
    reported_symptoms: mergeSymptoms(pending.reported_symptoms ?? [], symptoms),
  };
}
