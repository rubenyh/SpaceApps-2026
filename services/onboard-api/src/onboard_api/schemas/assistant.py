"""Contract of POST /assistant/messages.

Mirrored by apps/spaceship-app/src/api/types.ts. Plan field names map as:
`answer` -> `reply`, `data_warnings` -> `data_notices`. Every field added for
the medical workflow has a default, so older clients keep working.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

AssistantWorkflow = Literal["medical", "clarify", "unsupported"]

# No clinician is on board and the ground link may be down. immediate: emergency,
# act now with the steps and the mission emergency procedure. review_required: act
# with the steps and keep monitoring; send the report when a link exists.
# undetermined: a decisive datum is missing. informational: general information only.
Urgency = Literal["immediate", "review_required", "undetermined", "informational"]
SymptomStatus = Literal["present", "absent", "unknown"]
CandidateStatus = Literal["compatible", "rule_out", "insufficient_evidence"]

# Closed vocabulary shared by structured input, text interpretation and rules.
# Some codes are context, not symptoms (heat_exposure, intense_exertion,
# allergen_exposure, multiple_crew_symptoms, *_reported alerts).
SymptomCode = Literal[
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
]


class ReportedSymptom(BaseModel):
    """One structured observation. Overrides text interpretation of the same code."""

    symptom: SymptomCode
    status: SymptomStatus = "present"
    onset: Literal["sudden", "gradual"] | None = None
    severity: Literal["mild", "moderate", "severe"] | None = None
    persistence: Literal["ongoing", "resolved", "recurrent"] | None = None
    started_at: AwareDatetime | None = None
    context: str | None = Field(default=None, max_length=200)


class CaseObservation(BaseModel):
    """One observation of an open case, returned by the server and echoed back unchanged."""

    symptom: SymptomCode
    status: SymptomStatus
    # "text": rules on the message, "llm": local interpreter, "structured": reported_symptoms.
    origin: Literal["structured", "text", "llm"]
    # The user's words that support it ("structured" for structured input).
    evidence: str = Field(max_length=300)
    temporality: Literal["current", "resolved", "historical", "hypothetical"] = "current"
    subject: Literal["self", "other"] = "self"
    onset: Literal["sudden", "gradual"] | None = None
    severity: Literal["mild", "moderate", "severe"] | None = None
    persistence: Literal["ongoing", "resolved", "recurrent"] | None = None
    context: str | None = Field(default=None, max_length=200)


class Clarification(BaseModel):
    """Open case with a pending question. The endpoint keeps no conversation: the
    console sends this object back, unchanged, with the answer in `message`."""

    # "routing" (report or general info?), "symptom" (what do you feel?),
    # or "<protocol_id>.<question_key>" for a card question.
    question_id: str = Field(max_length=100)
    question: str = Field(max_length=500)
    # The case belongs to this person; another astronaut_id starts a new case.
    astronaut_id: str | None = None
    observations: list[CaseObservation] = Field(default_factory=list, max_length=60)


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # Person being assessed.
    astronaut_id: str | None = None
    # Crewmate who sends the report, when it is not the assessed person.
    reported_by: str | None = None
    # To answer a clarifying question, send back `clarification` (below). Older
    # clients resend the original message plus the new structured data.
    reported_symptoms: list[ReportedSymptom] = Field(default_factory=list, max_length=40)
    # `clarification` from the previous response, to answer its question. Then
    # `message` holds only the answer (resending the original text also works).
    clarification: Clarification | None = None


class GuideSource(BaseModel):
    """A protocol card (kind="protocol") or a retrieved corpus chunk (kind="guide")."""

    id: str
    title: str
    section: str | None = None
    url: str | None = None
    kind: Literal["protocol", "guide"] = "guide"


class MatchedRule(BaseModel):
    rule_id: str
    protocol_id: str
    protocol_version: str
    urgency: Urgency


# Evidence quality of a finding. simulated: `simulated:*` or `demo` source;
# stale: old or future-dated reading; poor_quality: quality != "good";
# missing: the reading (or the whole repository) is not available.
EvidenceFlag = Literal["simulated", "stale", "missing", "poor_quality"]


class Finding(BaseModel):
    kind: Literal["symptom", "reading", "event", "data_gap"]
    detail: str
    # "report" (text), "structured", "sqlite:<kind>", "event:<id>".
    source: str
    evidence_flags: list[EvidenceFlag] = []


class PossibleCause(BaseModel):
    """Candidate from the protocol's reviewed catalog. Never a probability."""

    id: str
    label: str
    status: CandidateStatus
    evidence_for: list[str] = []
    missing_data: list[str] = []
    source_ids: list[str] = []


class ActionStep(BaseModel):
    """One cited checklist step from a versioned protocol card."""

    text: str
    # self: one awake astronaut alone. crew: needs another crew member. equipment: needs a device or kit.
    who: Literal["self", "crew", "equipment"]
    # GuideSource ids ("<protocol_id>@<version>#<source_id>") in `sources`.
    source_ids: list[str] = []


class MissionProcedure(BaseModel):
    """Mission procedure an action points to. `loaded=False`: its text is not in the
    assistant, so the console names it and the crew uses the mission's own copy."""

    title: str
    loaded: bool = False


class KnowledgeVersion(BaseModel):
    """Approved knowledge bundle active onboard (contracts/medical-eval section 5)."""

    candidate_id: str
    digest: str


class CaseReport(BaseModel):
    """Plain-text report built deterministically from the case, for the astronaut to copy."""

    text: str
    # Active approved bundle when the report was made; null when none is active.
    knowledge_version: KnowledgeVersion | None = None
    # Nothing transmits it yet. Only a real delivery mechanism that confirms
    # transmission may set another value.
    transmission: Literal["not_sent"] = "not_sent"


class IncidentRef(BaseModel):
    """Onboard incident stored for an `immediate` response. recorded=False keeps the
    action and steps in the response and says why nothing was stored."""

    id: str | None = None
    recorded: bool
    error: str | None = None


class AssistantResponse(BaseModel):
    """Same shape for every workflow. New workflows add a `workflow` value."""

    reply: str
    workflow: AssistantWorkflow
    needs_clarification: bool
    sources: list[GuideSource] = []
    data_notices: list[str] = []
    disclaimer: str | None = None
    urgency: Urgency | None = None
    action: str | None = None
    # Who to tell, e.g. "crew". Nothing is transmitted.
    notify: list[str] = []
    # Cited checklist of the action, in order. Separate self / crew / equipment.
    steps: list[ActionStep] = []
    mission_procedures: list[MissionProcedure] = []
    # Guidance the cards cannot give, stated explicitly.
    missing_guidance: list[str] = []
    report: CaseReport | None = None
    protocol_id: str | None = None
    additional_protocol_ids: list[str] = []
    matched_rules: list[MatchedRule] = []
    findings: list[Finding] = []
    possible_causes: list[PossibleCause] = []
    clarifying_question: str | None = None
    # Set with needs_clarification on medical/clarify replies: send it back unchanged.
    clarification: Clarification | None = None
    # Set only when urgency == "immediate".
    incident: IncidentRef | None = None


class OperationalEvent(BaseModel):
    """Ship event from the application (or a labeled demo fixture), never from chat text."""

    id: str
    type: Literal["cabin_pressure", "cabin_smoke", "cabin_co2", "cabin_air_other", "radiation"]
    origin: str  # e.g. "ship:eclss", "dosimeter:area-2"
    occurred_at: AwareDatetime
    status: Literal["active", "resolved"]
    provenance: Literal["confirmed", "simulated"]
    # Empty: the whole cabin.
    astronaut_ids: list[str] = []
