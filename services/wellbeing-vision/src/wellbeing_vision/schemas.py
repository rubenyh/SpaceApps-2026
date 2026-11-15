"""Payloads sent to onboard-api, per docs/wellbeing-contract.md (branch agent/hiram/wellbeing-backend).
Unmeasurable values are None, never 0. "unknown-<track>" ids are accepted but never enter a baseline."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field

from wellbeing_vision.config import ASTRONAUT_ID_PATTERN

Quality = Literal["good", "suspect", "bad"]
AstronautId = Annotated[str, Field(pattern=ASTRONAUT_ID_PATTERN)]


class Identity(BaseModel):
    method: Literal["face", "wearable", "manual"]
    match_score: float | None = Field(default=None, ge=0, le=1)


class Fatigue(BaseModel):
    blink_rate_per_min: float | None = Field(ge=0)
    perclos: float | None = Field(ge=0, le=1)
    eye_openness_vs_neutral: float | None = Field(ge=0)
    yawn_count: int | None = Field(ge=0)
    nod_count: int | None = Field(ge=0)


class Tension(BaseModel):
    brow_lower_delta: float | None = Field(ge=0, le=1)
    lip_press_delta: float | None = Field(ge=0, le=1)
    # Optional in the contract: highest level held >= 1 s; None if never held 1 s with the face visible.
    brow_lower_peak_1s: float | None = Field(None, ge=0, le=1)
    lip_press_peak_1s: float | None = Field(None, ge=0, le=1)


class Motion(BaseModel):
    speed: float | None = Field(default=None, ge=0)  # approx. shoulder widths per second
    stationary_ratio: float | None = Field(default=None, ge=0, le=1)
    fidget_index: float | None = Field(default=None, ge=0)
    torso_angle_dev: float | None = Field(default=None, ge=0)  # degrees vs own neutral posture


class VisionSession(BaseModel):
    astronaut_id: AstronautId
    session_type: Literal["bitacora", "ambiente"]
    module_id: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=64)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    quality: Quality
    valid_frame_ratio: float = Field(ge=0, le=1)
    identity: Identity
    # False: the backend ignores neutral-relative metrics (eye_openness_vs_neutral, tension.*).
    neutral_ok: bool
    fatigue: Fatigue | None
    tension: Tension | None
    motion: Motion | None = None
    provisional: bool = True


class CoPresenceOccupant(BaseModel):
    astronaut_id: AstronautId
    seconds_present: float = Field(ge=0)


class CoPresencePair(BaseModel):
    a: AstronautId
    b: AstronautId
    seconds_together: float = Field(ge=0)
    mean_distance_shoulders: float | None = None  # approximate, monocular
    facing_ratio: float | None = Field(default=None, ge=0, le=1)  # 2D approximation


class CoPresence(BaseModel):
    module_id: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime
    window_end: AwareDatetime
    occupants: list[CoPresenceOccupant]
    pairs: list[CoPresencePair]
    quality: Quality = "good"
    provisional: bool = True
