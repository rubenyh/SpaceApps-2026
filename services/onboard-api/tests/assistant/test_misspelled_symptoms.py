"""Misspelled and voice-transcribed symptom reports through POST /assistant/messages.

Ollama is down in every test (FailingLLM): the rules alone must read the report, and a
confident correction must reach the same assessment as the correctly spelled text.
"""

import pytest

from assistant.fakes import FailingLLM
from assistant.test_post_cases import ask  # noqa: F401  (fixture)

# Fields that make up the assessment; data_notices differ (they name the correction).
_DECISION = ("workflow", "protocol_id", "additional_protocol_ids", "urgency", "action",
             "matched_rules", "needs_clarification", "clarifying_question")


def send(ask, message: str) -> dict:
    body, *_ = ask({"message": message, "astronaut_id": "ana"}, llm=FailingLLM())
    return body


def decision(body: dict) -> dict:
    return {k: body[k] for k in _DECISION}


def test_reported_dyziness_example(ask) -> None:
    before_fix = send(ask, "i am having some dyziness")
    spelled = send(ask, "i have some dizziness")
    assert spelled["protocol_id"] == "dizziness_or_space_motion_sickness"
    assert before_fix["workflow"] == "medical"
    assert decision(before_fix) == decision(send(ask, "i am having some dizziness"))
    assert before_fix["protocol_id"] == spelled["protocol_id"]
    assert before_fix["urgency"] == spelled["urgency"]
    assert 'Read "dyziness" as "dizziness".' in before_fix["data_notices"]


@pytest.mark.parametrize(
    ("typo", "spelled"),
    [
        # typed typos across the catalog
        ("I have a terrible hedache", "I have a terrible headache"),
        ("I feel nausious", "I feel nauseous"),
        ("I have diarhea and I keep vomitting", "I have diarrhea and I keep vomiting"),
        ("my heart has palpatations", "my heart has palpitations"),
        ("I feel feverrish", "I feel feverish"),
        ("I have been coughhing all day", "I have been coughing all day"),
        ("I have leg crampps", "I have leg cramps"),
        ("I have trouble breating", "I have trouble breathing"),
        ("tengo diarea", "tengo diarrea"),
        ("estoy mariado", "estoy mareado"),
        # voice-transcription variants
        ("I have a head ache", "I have a headache"),
        ("I can not breathe", "I cannot breathe"),
        # alarm paths
        ("I cant breath", "I can't breathe"),
        ("my crewmate is unconsious", "my crewmate is unconscious"),
        ("she is having a siezure", "she is having a seizure"),
        ("my hand is bleding heavily", "my hand is bleeding heavily"),
        ("I have slured speech", "I have slurred speech"),
        # negation, hypothetical, timing and severity come from the report itself
        ("I don't have any dyziness", "I don't have any dizziness"),
        ("what should I do if I get dyziness", "what should I do if I get dizziness"),
        ("severe dyziness since yesterday", "severe dizziness since yesterday"),
        ("I had a hedache but it went away", "I had a headache but it went away"),
    ],
)
def test_typo_reaches_same_assessment(ask, typo: str, spelled: str) -> None:
    got, want = send(ask, typo), send(ask, spelled)
    assert want["workflow"] == "medical", want
    assert decision(got) == decision(want)


@pytest.mark.parametrize(
    "message", ["my crewmate is unconsious", "she is having a siezure", "I cant breath"]
)
def test_misspelled_alarm_with_ollama_down(ask, message: str) -> None:
    body = send(ask, message)
    assert body["urgency"] == "immediate", body


@pytest.mark.parametrize(
    "message",
    ["I am having some pizza", "the monitor is bleeping", "I keep failing the test"],
)
def test_lookalikes_stay_unsupported(ask, message: str) -> None:
    assert send(ask, message)["workflow"] == "unsupported"


def test_hypothetical_is_not_a_current_report(ask) -> None:
    body = send(ask, "what should I do if I get dyziness")
    assert body["urgency"] in (None, "informational"), body


def test_ambiguous_word_asks_one_question(ask) -> None:
    body = send(ask, "I have been coumping")
    assert body["workflow"] == "medical"
    assert body["needs_clarification"]
    assert body["clarifying_question"] == "Do you mean cough or cramps?"
    assert body["urgency"] == "undetermined"
