"""Contract of POST /assistant/messages.

Mirrored by apps/spaceship-app/src/api/types.ts. Plan field names map as:
`answer` -> `reply`, `data_warnings` -> `data_notices`. Every field added for
the medical workflow has a default, so older clients keep working.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

AssistantWorkflow = Literal["medical", "clarify", "unsupported"]

# immediate: alert on board now. review_required: ask the crew medical officer
# for a review (priority is stated in `action`). undetermined: a decisive datum
# is missing. informational: general information only.
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


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # Person being assessed.
    astronaut_id: str | None = None
    # Crewmate who sends the report, when it is not the assessed person.
    reported_by: str | None = None
    # To answer a clarifying question, resend the original message plus the
    # new structured data (the endpoint is stateless).
    reported_symptoms: list[ReportedSymptom] = Field(default_factory=list, max_length=40)


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


class Finding(BaseModel):
    kind: Literal["symptom", "reading", "event", "data_gap"]
    detail: str
    # "report" (text), "structured", "sqlite:<kind>", "event:<id>".
    source: str


class PossibleCause(BaseModel):
    """Candidate from the protocol's reviewed catalog. Never a probability."""

    id: str
    label: str
    status: CandidateStatus
    evidence_for: list[str] = []
    missing_data: list[str] = []
    source_ids: list[str] = []


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
    # Who to notify, e.g. "responsable médico a bordo". Nothing is transmitted.
    notify: list[str] = []
    protocol_id: str | None = None
    additional_protocol_ids: list[str] = []
    matched_rules: list[MatchedRule] = []
    findings: list[Finding] = []
    possible_causes: list[PossibleCause] = []
    clarifying_question: str | None = None


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
