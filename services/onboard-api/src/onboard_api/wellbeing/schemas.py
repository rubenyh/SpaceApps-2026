"""Wellbeing API contract. Documented in docs/wellbeing-contract.md.

The console mirrors these models in apps/spaceship-app/src/api/types.ts.
Change both (and the document) together.
"""

from datetime import date
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from onboard_api.schemas.readings import is_simulated_source  # noqa: F401 (re-exported)

Quality = Literal["good", "suspect", "bad"]
SupportLevel = Literal[
    "ok", "attention", "needs_support", "baseline_pending", "stale", "no_data"
]
IndicatorStatus = Literal["ok", "attention", "baseline_pending", "stale", "no_data"]
IndicatorKind = Literal["sleep", "fatigue", "stress", "activation", "social", "mood"]
WellbeingSource = Literal["checkin", "vision", "physiology", "social"]
Confidence = Literal["low", "medium", "high"]
Trend = Literal["improving", "stable", "worsening", "unknown"]
AdverseDirection = Literal["low", "high", "both"]
SignalKind = Literal["hrv_sdnn", "resting_heart_rate", "sleep_hours"]
VisionSessionType = Literal["bitacora", "ambiente"]
# Where a value came from. "mixed": live and simulated data on the same day.
Origin = Literal["live", "simulated", "mixed"]
IdentityMethod = Literal["face", "wearable", "manual"]

INDICATOR_KINDS: tuple[IndicatorKind, ...] = (
    "sleep",
    "fatigue",
    "stress",
    "activation",
    "social",
    "mood",
)
SOURCES: tuple[WellbeingSource, ...] = ("checkin", "vision", "physiology", "social")
SIGNAL_UNITS: dict[SignalKind, str] = {
    "hrv_sdnn": "ms",
    "resting_heart_rate": "bpm",
    "sleep_hours": "h",
}

_Scale = Field(ge=0, le=4)
_SourceField = Field(min_length=1, max_length=64)
_Ratio = Field(default=None, ge=0, le=1)
_NonNegative = Field(default=None, ge=0)


# --- Parameters and check-in form ---


class ComponentParameter(BaseModel):
    component: str
    source: WellbeingSource
    indicator: IndicatorKind
    adverse_direction: AdverseDirection
    scale_floor: float
    unit: str


class WellbeingParameters(BaseModel):
    provisional: bool = True
    basis: str
    # IANA zone of the mission day all inputs are grouped by.
    mission_tz: str
    z_threshold: float
    sustain_days: int
    baseline_days: int
    baseline_min_days: int
    adaptation_days: int
    stale_after_days: int
    trend_window_days: int
    trend_min_delta: float
    z_cap: float
    components: list[ComponentParameter]


class CheckinFormItem(BaseModel):
    key: str
    prompt: str
    kind: Literal["hours", "scale", "text"]
    min: float | None = None
    max: float | None = None
    step: float | None = None
    min_label: str | None = None
    max_label: str | None = None
    higher_is_better: bool | None = None
    max_length: int | None = None
    optional: bool | None = None


class CheckinForm(BaseModel):
    version: str
    estimated_seconds: int
    items: list[CheckinFormItem]


# --- Inputs ---


class CheckinUpsert(BaseModel):
    sleep_hours: float = Field(ge=0, le=24, multiple_of=0.5)
    sleep_quality: int = _Scale
    energy: int = _Scale
    mood: int = _Scale
    interest: int = _Scale
    stress: int = _Scale
    crew_connection: int = _Scale
    comment: str | None = Field(default=None, max_length=500)
    source: str = Field(default="crew", min_length=1, max_length=64)


class Checkin(CheckinUpsert):
    astronaut_id: str
    day: date
    submitted_at: AwareDatetime
    simulated: bool


class SignalCreate(BaseModel):
    astronaut_id: str
    kind: SignalKind
    value: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=16)
    recorded_at: AwareDatetime
    quality: Quality
    source: str = _SourceField

    @model_validator(mode="after")
    def _unit_matches_kind(self) -> Self:
        expected = SIGNAL_UNITS[self.kind]
        if self.unit != expected:
            raise ValueError(f"unit for '{self.kind}' must be '{expected}'")
        return self


class Signal(SignalCreate):
    id: int
    received_at: AwareDatetime
    simulated: bool


UNKNOWN_PREFIX = "unknown-"
_PersonId = Field(min_length=1, max_length=48)
_ModuleId = Field(min_length=1, max_length=32)


def is_unknown_person(astronaut_id: str) -> bool:
    """Unidentified tracks from the vision process: stored, never baselined."""
    return astronaut_id.startswith(UNKNOWN_PREFIX)


class VisionIdentity(BaseModel):
    method: IdentityMethod
    match_score: float | None = _Ratio


class VisionFatigue(BaseModel):
    blink_rate_per_min: float | None = _NonNegative
    perclos: float | None = _Ratio
    eye_openness_vs_neutral: float | None = _NonNegative
    yawn_count: int | None = _NonNegative
    nod_count: int | None = _NonNegative


class VisionTension(BaseModel):
    brow_lower_delta: float | None = _Ratio
    lip_press_delta: float | None = _Ratio
    # Highest level held for at least 1 s; None if never 1 s with the face
    # visible. Optional so older senders keep working.
    brow_lower_peak_1s: float | None = _Ratio
    lip_press_peak_1s: float | None = _Ratio


class VisionMotion(BaseModel):
    speed: float | None = _NonNegative
    stationary_ratio: float | None = _Ratio
    fidget_index: float | None = _NonNegative
    torso_angle_dev: float | None = _NonNegative


class VisionSessionCreate(BaseModel):
    """Shape proposed by the vision process. Derived metrics only, no images."""

    astronaut_id: str = _PersonId
    session_type: VisionSessionType
    module_id: str = _ModuleId
    source: str = _SourceField
    started_at: AwareDatetime
    ended_at: AwareDatetime
    quality: Quality
    valid_frame_ratio: float = Field(ge=0, le=1)
    identity: VisionIdentity
    neutral_ok: bool
    fatigue: VisionFatigue | None = None
    tension: VisionTension | None = None
    motion: VisionMotion | None = None
    provisional: bool = True

    @model_validator(mode="after")
    def _valid_session(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not be before started_at")
        if self.fatigue is None and self.tension is None and self.motion is None:
            raise ValueError("at least one of fatigue, tension or motion must be set")
        return self


class VisionSession(VisionSessionCreate):
    id: int
    received_at: AwareDatetime
    simulated: bool


class CoPresenceOccupant(BaseModel):
    astronaut_id: str = _PersonId
    seconds_present: float = Field(ge=0)


class CoPresencePair(BaseModel):
    a: str = _PersonId
    b: str = _PersonId
    seconds_together: float = Field(ge=0)
    mean_distance_shoulders: float | None = _NonNegative
    facing_ratio: float | None = _Ratio


class CoPresenceCreate(BaseModel):
    """One module window (60 s), as sent by the vision process."""

    module_id: str = _ModuleId
    source: str = _SourceField
    window_start: AwareDatetime
    window_end: AwareDatetime
    occupants: list[CoPresenceOccupant] = Field(min_length=1, max_length=16)
    pairs: list[CoPresencePair] = Field(default_factory=list, max_length=120)
    quality: Quality = "good"
    provisional: bool = True

    @model_validator(mode="after")
    def _valid_window(self) -> Self:
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        length = (self.window_end - self.window_start).total_seconds()
        ids = [o.astronaut_id for o in self.occupants]
        if len(set(ids)) != len(ids):
            raise ValueError("occupants must not repeat")
        if any(o.seconds_present > length for o in self.occupants):
            raise ValueError("seconds_present exceeds the window length")
        for pair in self.pairs:
            if pair.a == pair.b or pair.a not in ids or pair.b not in ids:
                raise ValueError("each pair must be two different occupants")
            if pair.seconds_together > length:
                raise ValueError("seconds_together exceeds the window length")
        return self


class CoPresence(CoPresenceCreate):
    id: int
    received_at: AwareDatetime
    simulated: bool


# --- Outputs ---


class CrewMemberSummary(BaseModel):
    astronaut_id: str
    display_name: str
    level: SupportLevel
    trend: Trend
    # Origin of the latest day with data: show EN VIVO for live/mixed.
    latest_origin: Origin | None


class CrewWellbeing(BaseModel):
    generated_at: AwareDatetime
    provisional: bool = True
    members: list[CrewMemberSummary]


class ComponentState(BaseModel):
    component: str
    source: WellbeingSource
    latest_value: float | None
    unit: str
    z: float | None
    baseline_median: float | None
    baseline_scale: float | None
    baseline_days: int
    baseline_from: date | None
    baseline_to: date | None
    baseline_ready: bool
    latest_day: date | None
    latest_origin: Origin | None


class IndicatorState(BaseModel):
    kind: IndicatorKind
    status: IndicatorStatus
    z: float | None
    deviant_since: date | None
    sources: list[WellbeingSource]
    latest_day: date | None
    latest_origin: Origin | None
    provisional: bool = True
    components: list[ComponentState]


class WellbeingAssessment(BaseModel):
    astronaut_id: str
    generated_at: AwareDatetime
    level: SupportLevel
    confidence: Confidence
    trend: Trend
    onset_date: date | None
    sustained_days: int
    discrepancy: bool
    sustained_sources: list[WellbeingSource]
    latest_day: date | None
    indicators: list[IndicatorState]
    support_notes: list[str]
    data_notices: list[str]
    latest_origin: Origin | None
    # Disjoint day counts: only live data, only simulated data, or both.
    live_days: int
    simulated_days: int
    mixed_days: int
    provisional: bool = True


class TimelineDay(BaseModel):
    day: date
    level: SupportLevel
    has_data: bool
    has_checkin: bool
    origin: Origin | None
    indicators: dict[IndicatorKind, float | None]
    sources: dict[WellbeingSource, float | None]


class WellbeingTimeline(BaseModel):
    astronaut_id: str
    generated_at: AwareDatetime
    onset_date: date | None
    z_threshold: float
    provisional: bool = True
    days: list[TimelineDay]


# --- Ground psychologist packages (manual, consent required) ---

GroundRequester = Literal["self", "captain", "ground_psychologist"]
GroundInclude = Literal["assessment", "timeline", "checkins", "comments"]
GroundPackageStatus = Literal["queued", "withdrawn", "sent"]


class GroundConsent(BaseModel):
    astronaut_confirmed: bool
    statement_version: str = Field(min_length=1, max_length=16)


class GroundPackageCreate(BaseModel):
    astronaut_id: str
    requested_by: GroundRequester
    requested_by_name: str = Field(min_length=1, max_length=80)
    consent: GroundConsent
    period_from: date
    period_to: date
    include: list[GroundInclude] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _valid_request(self) -> Self:
        # Never sent, never even queued, without the astronaut's own consent.
        if not self.consent.astronaut_confirmed:
            raise ValueError("explicit consent from the astronaut is required")
        if self.period_to < self.period_from:
            raise ValueError("period_to must not be before period_from")
        if len(set(self.include)) != len(self.include):
            raise ValueError("include must not repeat")
        if "comments" in self.include and "checkins" not in self.include:
            raise ValueError("'comments' requires 'checkins'")
        return self


class GroundPackage(BaseModel):
    id: str
    astronaut_id: str
    requested_by: GroundRequester
    requested_by_name: str
    period_from: date
    period_to: date
    include: list[GroundInclude]
    note: str | None
    status: GroundPackageStatus
    consent_statement_version: str
    consent_recorded_at: AwareDatetime
    created_at: AwareDatetime


class GroundPackageContent(BaseModel):
    package: GroundPackage
    assessment: WellbeingAssessment | None
    timeline: WellbeingTimeline | None
    checkins: list[Checkin] | None
