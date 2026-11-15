"""The synthetic medical evaluation case set (eval/medical/cases/v1, contract section 1)."""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # locked through chromadb

from onboard_api.assistant.workflows.medical.protocols import load_catalog

ROOT = Path(__file__).resolve().parents[4] / "eval" / "medical"
CASES_DIR = ROOT / "cases" / "v1"
SCHEMA = json.loads((CASES_DIR / "case.schema.json").read_text(encoding="utf-8"))
PATHS = sorted(p for p in CASES_DIR.rglob("*.json") if p.name != "case.schema.json")
CASES = [json.loads(p.read_text(encoding="utf-8")) for p in PATHS]
REQUIRED_TAGS = {
    "typo", "transcription", "follow_up", "conflicting_readings", "stale_readings", "simulated_data",
    "missing_equipment", "dependency_down", "negation", "hypothetical", "alarm", "near_miss",
}
CARD_TEXT = " ".join(
    t for card in load_catalog().values() for a in card.actions.values() for t in [a.text, *(s.text for s in a.steps)]
).lower()
STALE_AFTER_SECONDS = 300  # pulse and SpO2 policy (tests/assistant/medical_cases.py)


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_case_matches_schema_and_location(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    errors = [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(SCHEMA).iter_errors(case)]
    assert errors == []
    assert path.stem == case["case_id"] and path.parent.name == case["family"]
    expected = case["expected"]
    assert expected["protocol_id"] is None or expected["protocol_id"] in load_catalog()
    # Guide chunk prefixes only: protocol card sources always count as supported.
    assert not any("@" in s or s.startswith("protocol") for s in expected["acceptable_sources"])
    # Matched case-insensitively: must not hit a negated safe phrase in any card ("do not hold them down").
    assert not [p for p in expected["prohibited_actions"] if p.lower() in CARD_TEXT]

    turns = case["turns"]
    assert not turns[0].get("use_previous_clarification")
    tags = set(case["tags"])
    assert ("follow_up" in tags) == any(t.get("use_previous_clarification") for t in turns[1:])
    if "simulated_data" in tags:
        assert any(r["source"].startswith("simulated:") for r in case["readings"]) or any(
            e["provenance"] == "simulated" for e in case["events"])
    if "stale_readings" in tags:
        assert any(r["age_seconds"] > STALE_AFTER_SECONDS for r in case["readings"])
    if "dependency_down" in tags:
        assert "down" in case["dependencies"].values()
    if "alarm" in tags:
        assert expected["urgency"] == "immediate"


def test_case_ids_are_unique() -> None:
    ids = [c["case_id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_every_protocol_family_is_covered() -> None:
    assert {c["family"] for c in CASES} == set(load_catalog())


def test_alarm_cards_have_alarm_or_near_miss_cases() -> None:
    for pid, card in load_catalog().items():
        if any(a.urgency == "immediate" for a in card.actions.values()):
            assert any(
                c["family"] == pid and {"alarm", "near_miss"} & set(c["tags"]) for c in CASES
            ), pid


def test_required_tags_appear() -> None:
    assert REQUIRED_TAGS <= {t for c in CASES for t in c["tags"]}


def test_review_log_lists_every_case() -> None:
    """eval/medical/README.md review log: one row per case with its current status and reviewer."""
    rows = re.findall(r"^\| `([^`]+)` \| (\w+) \| ([^|]*?) \| ([^|]*?) \|$",
                      (ROOT / "README.md").read_text(encoding="utf-8"), re.MULTILINE)
    log = {cid: (status, reviewer, date) for cid, status, reviewer, date in rows}
    assert set(log) == {c["case_id"] for c in CASES}
    for c in CASES:
        review = c["review"]
        assert log[c["case_id"]] == (review["status"], review["reviewer"] or "-", review["reviewed_at"] or "-")
