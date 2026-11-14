"""Payloads sent to onboard-api. Draft until docs/wellbeing-contract.md is published;
that contract wins. Unmeasurable values are None, never 0."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from wellbeing_vision.config import ASTRONAUT_ID_PATTERN

Quality = Literal["good", "suspect", "bad"]


class Identity(BaseModel):
    method: Literal["face", "manual"]
    match_score: float | None = None


class Fatigue(BaseModel):
    blink_rate_per_min: float | None
    perclos: float | None
    eye_openness_vs_neutral: float | None
    yawn_count: int | None
    nod_count: int | None


class Tension(BaseModel):
    brow_lower_delta: float | None
    lip_press_delta: float | None


class VisionSession(BaseModel):
    astronaut_id: str = Field(pattern=ASTRONAUT_ID_PATTERN)
    session_type: Literal["bitacora", "ambient"]
    module_id: str | None
    source: str = Field(min_length=1, max_length=64)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    quality: Quality
    valid_frame_ratio: float = Field(ge=0, le=1)
    identity: Identity
    neutral_ok: bool | None
    fatigue: Fatigue | None
    tension: Tension | None
    motion: dict | None = None
    # Thresholds are not clinically validated.
    provisional: bool = True
