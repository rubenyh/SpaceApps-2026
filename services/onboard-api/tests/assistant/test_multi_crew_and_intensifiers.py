"""English multi-crew reports and Spanish pain intensifiers through POST /assistant/messages
(issue #73). Ollama is down in every test: the rules alone decide."""

import pytest

from assistant.fakes import FailingLLM
from assistant.test_post_cases import ask  # noqa: F401  (fixture)

CABIN = "cabin_environment_alert"


def send(ask, message: str) -> dict:
    body, *_ = ask({"message": message, "astronaut_id": "ana"}, llm=FailingLLM())
    return body


def cards(body: dict) -> list:
    return [body["protocol_id"], *body["additional_protocol_ids"]]


@pytest.mark.parametrize(
    "message",
    [
        "Several of us have headaches and nausea",  # eval case cabin.alarm.005
        "We all feel sick",
        "Everyone here has a headache",
        "The whole crew is dizzy",
        "Both of us have nausea",
        "Varios tripulantes tenemos dolor de cabeza y náuseas",  # Spanish still works
    ],
)
def test_multi_crew_symptoms_raise_cabin_alarm(ask, message: str) -> None:
    body = send(ask, message)
    assert body["urgency"] == "immediate", body
    assert CABIN in cards(body), body


@pytest.mark.parametrize(
    "message",
    [
        "Several of us are going to dinner",
        "Several of us don't have headaches",
        "What if several of us get headaches?",
        "Todos tenemos hambre",
    ],
)
def test_multi_crew_without_a_current_complaint_is_no_alarm(ask, message: str) -> None:
    body = send(ask, message)
    assert body["urgency"] != "immediate", body
    assert CABIN not in cards(body), body


@pytest.mark.parametrize(
    ("message", "card"),
    [
        ("Me duele mucho el estómago desde ayer", "abdominal_pain_or_gi_bleeding"),  # abdominal.stale.001
        ("Me duele bastante la barriga", "abdominal_pain_or_gi_bleeding"),
        ("Me duele mucho el costado", "urinary_symptoms"),
    ],
)
def test_spanish_intensifier_reaches_the_card(ask, message: str, card: str) -> None:
    body = send(ask, message)
    assert body["workflow"] == "medical"
    assert card in cards(body), body


@pytest.mark.parametrize(
    ("intensified", "plain"),
    [
        ("No me duele mucho el estómago", "No me duele el estómago"),
        ("Me duele un poco la cabeza", "Tengo un dolor de cabeza leve"),
    ],
)
def test_intensifier_reads_like_the_plain_phrase(ask, intensified: str, plain: str) -> None:
    got, want = send(ask, intensified), send(ask, plain)
    assert (got["workflow"], got["protocol_id"], got["urgency"]) == (
        want["workflow"], want["protocol_id"], want["urgency"])
