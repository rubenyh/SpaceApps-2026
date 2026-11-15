"""Multi-turn cases through POST /assistant/messages.

The endpoint keeps no conversation: each reply with a pending question carries
`clarification`, and the next POST sends it back unchanged with the answer.
Qwen is replaced by FakeLLM(json_reply=...) (see test_ollama.py for the client).
"""

import json

import pytest
from fastapi.testclient import TestClient

from assistant.fakes import FailingReadings, FakeLLM, Forbidden
from assistant.medical_cases import _reading
from assistant.test_post_cases import post
from onboard_api.assistant.routing import CLARIFY_QUESTION
from onboard_api.assistant.workflows.medical import prompts
from onboard_api.assistant.workflows.medical.triage import GENERIC_CLARIFYING_QUESTION

BREATHING_Q = "breathing_difficulty.symptoms_and_repeat"


def qwen(*observations: tuple[str, str, str], other: str | None = None) -> FakeLLM:
    """Fake interpreter returning (symptom, status, evidence) observations."""
    obs = [{"symptom": s, "status": st, "evidence": ev} for s, st, ev in observations]
    return FakeLLM(json_reply=json.dumps({"observations": obs, "other_complaint": other}))


@pytest.fixture
def ask(client: TestClient, astronaut: str, db_path):
    def send(message: str, previous: dict | None = None, astronaut_id: str = "ana", **kw):
        request = {"astronaut_id": astronaut_id, "message": message}
        if previous is not None:
            request["clarification"] = previous["clarification"]
        return post(client, db_path, request, **kw)

    return send


def symptoms(body: dict) -> dict[str, str]:
    return {o["symptom"]: o["status"] for o in body["clarification"]["observations"]}


# --- hola -> malestar físico -> algo me aprieta el pecho ---


@pytest.mark.parametrize(
    "llm",
    [qwen(), FakeLLM(), qwen(("malaise", "present", "malestar físico"), other="malestar físico")],
    ids=["qwen-empty", "qwen-down", "qwen-maps-vague-text"],
)
def test_hola_then_malestar_fisico_asks_what_the_person_feels(ask, llm) -> None:
    hola, *_ = ask("hola")
    assert hola["workflow"] == "clarify" and hola["needs_clarification"]
    assert hola["clarification"]["question_id"] == "routing"

    # A muscle-sensor reading exists but says nothing about this question.
    body, _, llm, _ = ask("malestar físico", hola, llm=llm,
                          readings=[_reading("muscle_density", 42, "au")])
    assert body["workflow"] == "medical"
    assert body["needs_clarification"] and body["urgency"] == "undetermined"
    assert body["clarifying_question"] == GENERIC_CLARIFYING_QUESTION
    assert body["clarification"]["question_id"] == "symptom"
    assert body["action"] != prompts.OUT_OF_COVERAGE_ACTION
    assert body["data_notices"] == []
    assert CLARIFY_QUESTION in llm.json_calls[0]  # Qwen saw the pending question


def test_malestar_then_chest_tightness_applies_chest_card_before_qwen(ask) -> None:
    first, *_ = ask("malestar físico", llm=qwen())
    llm = qwen()
    body, readings, llm, retriever = ask("algo me aprieta el pecho", first, llm=llm)
    assert body["urgency"] == "immediate" and body["protocol_id"] == "chest_pain"
    assert not body["needs_clarification"] and body["clarification"] is None
    # Alarm from the rules: no wait for Qwen, SQLite, ChromaDB or the draft.
    assert llm.json_calls == [] and llm.calls == [] and readings.calls <= 1 and retriever.calls == []


# --- pending question about breathing difficulty ---


@pytest.fixture
def breathing(ask):
    """SpO2 88 % -> the card asks about shortness of breath."""
    body, *_ = ask("el oxímetro marca 88", llm=qwen(),
                   readings=[_reading("spo2", 88, "%"), _reading("heart_rate", 80, "bpm")])
    assert body["clarification"]["question_id"] == BREATHING_Q
    return body


def test_yes_a_little_means_mild_shortness_of_breath(ask, breathing) -> None:
    llm = qwen(("shortness_of_breath", "present", "sí, un poco"))
    body, *_ = ask("sí, un poco", breathing, llm=llm)
    assert body["urgency"] == "review_required" and body["protocol_id"] == "breathing_difficulty"
    assert any(f["detail"].startswith("Shortness of breath") for f in body["findings"])
    assert "shortness of breath" in llm.json_calls[0]  # Qwen got the pending question


def test_no_means_absent_and_keeps_the_reading_question(ask, breathing) -> None:
    body, *_ = ask("no", breathing, llm=qwen(("shortness_of_breath", "absent", "no")))
    assert body["urgency"] == "undetermined" and body["needs_clarification"]
    assert symptoms(body)["shortness_of_breath"] == "absent"
    assert body["clarification"]["question_id"] == BREATHING_Q


def test_yes_a_lot_from_qwen_is_rechecked_as_an_alarm(ask, breathing) -> None:
    llm = qwen(("shortness_of_breath", "present", "sí, mucho"))
    body, readings, *_ = ask("sí, mucho", breathing, llm=llm)
    assert body["urgency"] == "immediate" and body["protocol_id"] == "breathing_difficulty"
    assert readings.calls <= 1


def test_bare_yes_never_applies_to_a_symptom_that_was_not_asked(ask, breathing) -> None:
    body, *_ = ask("sí", breathing, llm=qwen(("chest_pain", "present", "sí")))
    assert body["urgency"] == "review_required" and body["protocol_id"] == "breathing_difficulty"
    assert "chest_pain" not in body["additional_protocol_ids"]
    assert not any("Chest pain" in f["detail"] for f in body["findings"])


@pytest.mark.parametrize(
    ("answer", "status", "urgency"),
    [("yes, a little", "present", "review_required"), ("no", "absent", "undetermined"),
     ("not sure", "unknown", "undetermined"), ("I don't know", "unknown", "undetermined"),
     ("yes, a lot", "present", "immediate")],
)
def test_english_short_replies_are_read_by_the_rules(ask, breathing, answer, status, urgency) -> None:
    """English bare answers work with the interpreter silent (rules only)."""
    body, *_ = ask(answer, breathing, llm=qwen())
    assert body["urgency"] == urgency and body["protocol_id"] == "breathing_difficulty"
    if body.get("clarification"):
        assert symptoms(body)["shortness_of_breath"] == status


@pytest.mark.parametrize("answer", ["sí, un poco", "no", "sí, mucho"])
def test_bare_answers_work_with_the_interpreter_down(ask, breathing, answer) -> None:
    body, *_ = ask(answer, breathing, llm=FakeLLM())
    expected = {"sí, un poco": "review_required", "no": "undetermined", "sí, mucho": "immediate"}
    assert body["urgency"] == expected[answer]


def test_follow_up_qualifies_the_open_symptom(ask) -> None:
    """'empezó de repente y es muy intenso' answers the headache question by the rules."""
    first, *_ = ask("me duele la cabeza", llm=FakeLLM())
    assert first["clarification"]["question_id"] == "neurologic_red_flags.headache_red_flags"
    body, readings, *_ = ask("empezó de repente y es muy intenso", first, llm=Forbidden("llm"))
    assert body["urgency"] == "immediate" and body["protocol_id"] == "neurologic_red_flags"
    assert readings.calls <= 1


# --- alarms interrupt a pending question, with every dependency down ---


@pytest.mark.parametrize("message", ["SOS", "auxilio", "no puedo respirar"])
def test_alarm_interrupts_pending_question_without_dependencies(ask, message) -> None:
    pending, *_ = ask("malestar físico", llm=qwen())
    llm, retriever = Forbidden("llm"), Forbidden("retriever")
    body, readings, *_ = ask(message, pending, llm=llm, retriever=retriever,
                             provider=FailingReadings())
    assert body["urgency"] == "immediate" and body["action"]
    assert not body["needs_clarification"]
    assert llm.calls == [] and retriever.calls == [] and readings.calls <= 1
    if message != "no puedo respirar":
        assert body["action"].startswith(prompts.SOS_ACTION)


def test_sos_keeps_the_card_alarms_of_the_case(ask, breathing) -> None:
    body, *_ = ask("SOS, me ahogo", breathing, llm=Forbidden("llm"))
    assert body["urgency"] == "immediate" and body["action"].startswith(prompts.SOS_ACTION)
    assert body["protocol_id"] == "breathing_difficulty"
    assert body["findings"][0]["detail"] == prompts.SOS_FINDING


# --- failures and separation ---


@pytest.mark.parametrize("reply", ["no es json", json.dumps({"observations": [
    {"symptom": "fever", "status": "present", "evidence": "tengo fiebre"}]})],
    ids=["invalid-json", "evidence-not-in-message"])
def test_bad_interpreter_output_keeps_the_case(ask, breathing, reply) -> None:
    body, *_ = ask("pues no sé", breathing, llm=FakeLLM(json_reply=reply))
    assert body["needs_clarification"]
    assert body["clarification"]["question_id"] == BREATHING_Q
    assert "fever" not in symptoms(body)
    # The case continues on the next POST.
    after, *_ = ask("sí, un poco", body, llm=qwen(("shortness_of_breath", "present", "sí, un poco")))
    assert after["urgency"] == "review_required"


def test_cases_of_two_astronauts_stay_separate(ask) -> None:
    luis, *_ = ask("me duele la cabeza", astronaut_id="luis", llm=qwen())
    ana, *_ = ask("malestar físico", llm=qwen())
    assert luis["clarification"]["astronaut_id"] == "luis" and "headache" in symptoms(luis)

    # Luis's case sent with Ana's id is ignored: Ana gets no headache.
    mixed, *_ = ask("sí", luis, llm=qwen())
    assert mixed["clarification"] is None or "headache" not in symptoms(mixed)
    assert "neurologic_red_flags" != mixed["protocol_id"]

    # Each case continues with its own observations.
    llm = qwen(("sudden_severe_headache", "present", "empezó de repente y es muy intenso"))
    luis2, *_ = ask("empezó de repente y es muy intenso", luis, astronaut_id="luis", llm=llm)
    assert luis2["urgency"] == "immediate" and luis2["protocol_id"] == "neurologic_red_flags"
    ana2, *_ = ask("me duele el oído", ana, llm=qwen())
    assert ana2["protocol_id"] is None and ana2["action"] == prompts.OUT_OF_COVERAGE_ACTION


def test_old_clients_without_clarification_still_work(ask) -> None:
    """Resending the original text plus the answer (previous contract) is not out of coverage."""
    body, *_ = ask("hola\nmalestar físico", llm=FakeLLM())
    assert body["clarifying_question"] == GENERIC_CLARIFYING_QUESTION


def test_general_question_after_routing_stays_educational(ask) -> None:
    hola, *_ = ask("hola")
    llm = qwen(("fever", "present", "la fiebre"))
    body, *_ = ask("información general sobre la fiebre", hola, llm=llm)
    assert body["urgency"] == "informational" and llm.json_calls == []


@pytest.mark.parametrize("message", ["I don't feel well", "I feel weird, something is off"])
def test_english_vague_report_asks_what_the_person_feels(ask, message) -> None:
    body, *_ = ask(message, llm=qwen())
    assert body["workflow"] == "medical" and body["needs_clarification"]
    assert body["clarifying_question"] == GENERIC_CLARIFYING_QUESTION


@pytest.mark.parametrize("message", ["What is dehydration?", "What causes a heart attack?"])
def test_english_educational_question_reaches_the_medical_workflow(ask, message) -> None:
    body, *_ = ask(message, llm=Forbidden("llm"))
    assert body["workflow"] == "medical" and body["urgency"] == "informational"
