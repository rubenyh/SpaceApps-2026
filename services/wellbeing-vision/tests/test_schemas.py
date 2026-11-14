"""The request examples from docs/wellbeing-contract.md must round-trip unchanged."""

import pytest
from pydantic import ValidationError

from wellbeing_vision.schemas import CoPresence, VisionSession

BITACORA = {
    "astronaut_id": "ast-01", "session_type": "bitacora", "module_id": "modulo-a", "source": "vision:cam0",
    "started_at": "2026-11-14T08:00:00Z", "ended_at": "2026-11-14T08:01:30Z", "quality": "good",
    "valid_frame_ratio": 0.94, "identity": {"method": "face", "match_score": 0.71}, "neutral_ok": True,
    "fatigue": {"blink_rate_per_min": 18.2, "perclos": 0.07, "eye_openness_vs_neutral": 0.88,
                "yawn_count": 1, "nod_count": 0},
    "tension": {"brow_lower_delta": 0.12, "lip_press_delta": 0.05},
    "motion": None, "provisional": True,
}
AMBIENTE_MOTION = {"speed": 0.35, "stationary_ratio": 0.6, "fidget_index": 0.12, "torso_angle_dev": 14.0}
CO_PRESENCE = {
    "module_id": "modulo-a", "source": "vision:cam0",
    "window_start": "2026-11-14T12:00:00Z", "window_end": "2026-11-14T12:01:00Z",
    "occupants": [{"astronaut_id": "ast-01", "seconds_present": 58},
                  {"astronaut_id": "unknown-3", "seconds_present": 45}],
    "pairs": [{"a": "ast-01", "b": "unknown-3", "seconds_together": 40,
               "mean_distance_shoulders": 2.3, "facing_ratio": 0.4}],
    "quality": "good", "provisional": True,
}


def _dump(model):
    return model.model_dump(mode="json")


def test_bitacora_example_matches_contract():
    out = _dump(VisionSession.model_validate(BITACORA))
    assert out | {"started_at": BITACORA["started_at"], "ended_at": BITACORA["ended_at"]} == BITACORA


def test_ambiente_motion_uses_contract_keys():
    s = VisionSession.model_validate(BITACORA | {"session_type": "ambiente", "fatigue": None,
                                                 "tension": None, "motion": AMBIENTE_MOTION})
    assert _dump(s)["motion"] == AMBIENTE_MOTION


def test_co_presence_example_and_default_quality():
    assert _dump(CoPresence.model_validate(CO_PRESENCE))["pairs"] == CO_PRESENCE["pairs"]
    no_quality = {k: v for k, v in CO_PRESENCE.items() if k != "quality"}
    assert CoPresence.model_validate(no_quality).quality == "good"


def test_negative_tension_is_rejected():
    with pytest.raises(ValidationError):
        VisionSession.model_validate(BITACORA | {"tension": {"brow_lower_delta": -0.1, "lip_press_delta": 0}})
