"""A message that says there are no symptoms gets no symptom from the LLM interpreter
(eval case urinary.simulated.001). The fake interpreter replies the way qwen2.5:3b did."""

import json

import pytest

from assistant.fakes import FailingLLM, FakeLLM
from assistant.test_post_cases import ask  # noqa: F401  (fixture)


def reading(evidence: str, symptom: str = "dark_urine") -> str:
    return json.dumps({"observations": [
        {"symptom": symptom, "status": "present", "evidence": evidence}]})


@pytest.mark.parametrize(
    ("message", "evidence"),
    [
        ("La muestra de orina salió de color rojizo pero no tengo síntomas",
         "orina salió de color rojizo"),
        ("My urine sample came out reddish but I have no symptoms", "urine sample came out reddish"),
        ("La orina salió rojiza, sin síntomas", "orina salió rojiza"),
    ],
)
def test_llm_symptom_is_dropped_when_the_message_denies_symptoms(ask, message, evidence) -> None:
    request = {"message": message, "astronaut_id": "ana"}
    got, *_ = ask(request, llm=FakeLLM(json_reply=reading(evidence)))
    rules, *_ = ask(request, llm=FailingLLM())
    assert got["protocol_id"] is None, got
    assert (got["urgency"], got["needs_clarification"]) == (rules["urgency"], rules["needs_clarification"])


def test_rule_symptom_still_counts_next_to_a_denial(ask) -> None:
    # Explicit text the rules read stays: the denial only blocks the interpreter's guesses.
    message = "Tengo la orina color cola, no tengo otros síntomas"
    body, *_ = ask({"message": message, "astronaut_id": "ana"}, llm=FakeLLM(json_reply='{"observations": []}'))
    assert body["protocol_id"] == "muscle_symptoms", body
