"""Types shared by the medical subgraph modules (interpret, triage, context, graph)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, TypedDict

from pydantic import BaseModel

from onboard_api.assistant.integrations import GuideChunk
from onboard_api.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
    CandidateStatus,
    Finding,
    GuideSource,
    MatchedRule,
    OperationalEvent,
    PossibleCause,
    SymptomCode,
    SymptomStatus,
    Urgency,
)

# current: happening now. resolved: acute sign that already passed (may still
# trigger an alarm, per card). historical: past episode. hypothetical: "qué pasa si".
Temporality = Literal["current", "resolved", "historical", "hypothetical"]
Route = Literal["alarm", "clarify", "assessment", "educational", "out_of_coverage"]


@dataclass(frozen=True)
class Observation:
    symptom: SymptomCode
    status: SymptomStatus
    origin: Literal["structured", "text"]
    evidence: str  # matched text span, or "structured"
    temporality: Temporality = "current"
    subject: Literal["self", "other"] = "self"
    onset: Literal["sudden", "gradual"] | None = None
    severity: Literal["mild", "moderate", "severe"] | None = None
    persistence: Literal["ongoing", "resolved", "recurrent"] | None = None
    context: str | None = None


@dataclass(frozen=True)
class Interpretation:
    observations: tuple[Observation, ...]
    # educational: a general question with no current symptom of the subject.
    # unclear: health-related but no recognised symptom ("no me siento bien").
    request_kind: Literal["report", "educational", "unclear"]
    # Message looks health related (symptom words, body, "médico", ...).
    medical_signal: bool
    # Sensor kinds the text mentions, e.g. ("spo2",) for "el oxímetro marca 88".
    mentions_readings: tuple[str, ...] = ()
    # Protocol id the text is about, used to filter retrieval topics.
    topic_hint: str | None = None


@dataclass(frozen=True)
class VitalReading:
    kind: str
    value: float | None
    value_text: str | None
    unit: str
    recorded_at: datetime
    quality: Literal["good", "suspect", "bad"]
    source: str
    age_seconds: int
    stale: bool  # older than sensor_config.stale_after_seconds (300 s demo policy)


@dataclass
class ReadingsContext:
    # False when the repository could not be read (missing DB, error, no astronaut_id).
    available: bool
    latest: dict[str, VitalReading] = field(default_factory=dict)  # by sensor kind
    warnings: list[str] = field(default_factory=list)  # Spanish, for data_notices


@dataclass(frozen=True)
class CandidateHit:
    candidate_id: str  # must exist in the protocol card's catalog
    status: CandidateStatus
    evidence_for: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleHit:
    rule_id: str  # "<protocol_id>.<rule>"
    protocol_id: str
    urgency: Urgency
    action_key: str  # key in Protocol.actions
    findings: tuple[Finding, ...] = ()
    candidates: tuple[CandidateHit, ...] = ()
    question_key: str | None = None  # key in Protocol.questions


# --- Versioned protocol cards (protocols/*.json) ---


class ProtocolSource(BaseModel):
    id: str
    title: str
    section: str
    url: str


class ProtocolAction(BaseModel):
    urgency: Urgency
    text: str
    notify: list[str] = []


class ProtocolCandidate(BaseModel):
    id: str
    label: str
    # Minimum evidence before the candidate can be shown as "compatible".
    minimum_evidence: str
    source_ids: list[str]


class Protocol(BaseModel):
    id: str
    version: str
    title: str
    # Lower = presented first among simultaneous immediate alarms.
    priority: int
    # Preserved card text, used verbatim when Ollama is unavailable.
    summary: str
    actions: dict[str, ProtocolAction]
    questions: dict[str, str] = {}
    candidates: list[ProtocolCandidate] = []
    sources: list[ProtocolSource]
    # Corpus chunk topics relevant to this card (ChromaDB metadata `topic`).
    guide_topics: list[str] = []


@dataclass
class Decision:
    """Deterministic outcome of the rules; the LLM never changes these fields."""

    urgency: Urgency
    protocol_id: str | None
    additional_protocol_ids: list[str]
    action: str | None
    notify: list[str]
    matched_rules: list[MatchedRule]
    findings: list[Finding]
    possible_causes: list[PossibleCause]
    clarifying_question: str | None
    protocol_sources: list[GuideSource]
    # Deterministic reply text built from the cards (action first).
    summary: str


# --- Injected dependencies ---


class ReadingsProvider(Protocol):
    def load(self, astronaut_id: str | None, now: datetime) -> ReadingsContext:
        """Never raises: failures become available=False plus a warning."""
        ...


class EventSource(Protocol):
    def active_events(self, now: datetime) -> list[OperationalEvent]:
        """Typed ship events known to the application. In-memory, no I/O wait."""
        ...


class MedicalState(TypedDict, total=False):
    request: AssistantRequest
    now: datetime
    events: list[OperationalEvent]
    interpretation: Interpretation
    alarm_hits: list[RuleHit]
    readings: ReadingsContext
    case_hits: list[RuleHit]
    route: Route
    decision: Decision
    guides: list[GuideChunk]
    notices: list[str]
    response: AssistantResponse
