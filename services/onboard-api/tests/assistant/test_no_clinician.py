"""No clinician on board, ground link not guaranteed (cards v2).

Exact console transcript hello -> symptom -> shortness of breath with a simulated SpO2
of 97 %, then severe breathing difficulty, missing readings, no ground link and Ollama /
ChromaDB down. Every answer must give the astronaut something to do, never refer to an
onboard clinician, keep unknown data unknown and report `not_sent`.
"""

import json

import pytest
from fastapi.testclient import TestClient

from assistant.fakes import FailingLLM, FailingReadings, FailingRetriever, FakeLLM, Forbidden, chunk
from assistant.medical_cases import FRESH, _reading
from assistant.test_post_cases import post
from onboard_api.assistant.workflows.medical import prompts
from onboard_api.assistant.workflows.medical.nodes import valid_draft
from onboard_api.config import Settings
from onboard_api.dependencies import get_clock
from onboard_api.main import create_app

SIM_SPO2 = {**_reading("spo2", 97, "%"), "source": "simulated:pulse-ox"}
SIM_HR = {**_reading("heart_rate", 78, "bpm"), "source": "simulated:pulse-ox"}
# Referrals to someone who is not on board (stating "no hay personal clínico a bordo" is fine).
CLINICIAN = ("responsable médico", "médico a bordo", "valoración médica", "consulta al médico", "doctor", "medical officer")


def no_clinician(body: dict) -> None:
    text = json.dumps({k: body[k] for k in ("reply", "action", "notify", "steps", "mission_procedures")},
                      ensure_ascii=False).lower()
    assert not any(w in text for w in CLINICIAN), text


def actionable(body: dict) -> None:
    """Action first, cited steps, at least one an astronaut alone can do, report not sent."""
    assert body["action"] and body["reply"].startswith(body["action"].split(" ")[0])
    assert body["steps"], body
    assert any(s["who"] == "self" for s in body["steps"])
    source_ids = {s["id"] for s in body["sources"]}
    for step in body["steps"]:
        assert step["source_ids"] and set(step["source_ids"]) <= source_ids, step
    assert body["report"]["transmission"] == "not_sent"
    assert "not_sent" in body["report"]["text"]
    no_clinician(body)


@pytest.fixture
def ask(client: TestClient, astronaut: str, db_path):
    def send(message: str, previous: dict | None = None, **kw):
        request = {"astronaut_id": "ana", "message": message}
        if previous is not None:
            request["clarification"] = previous["clarification"]
        return post(client, db_path, request, **kw)[0]

    return send


@pytest.mark.parametrize("llm", [FakeLLM(), FailingLLM()], ids=["qwen-silent", "ollama-down"])
def test_exact_transcript_with_simulated_spo2_97(ask, llm) -> None:
    hello = ask("hello", llm=llm)
    assert hello["needs_clarification"] and hello["clarification"]["question_id"] == "routing"
    symptom = ask("symptom", hello, llm=llm)
    assert symptom["needs_clarification"] and symptom["clarification"]["question_id"] == "symptom"

    body = ask("shortness of breath", symptom, llm=llm, retriever=FailingRetriever(),
               readings=[SIM_SPO2, SIM_HR])
    assert body["protocol_id"] == "breathing_difficulty"
    assert body["urgency"] == "review_required" and not body["needs_clarification"]
    actionable(body)
    assert body["mission_procedures"] and not body["mission_procedures"][0]["loaded"]

    report = body["report"]["text"]
    assert "Shortness of breath: present" in report
    # Unknown onset and severity stay unknown (never "mild" or "absent").
    assert "onset: unknown; intensity: unknown" in report
    assert "Onset of shortness of breath: unknown." in report
    assert "SpO₂: 97 %" in report and FRESH in report and "quality good" in report
    assert "source simulated:pulse-ox" in report and "SIMULATED" in report
    assert body["action"] in report
    [spo2] = [f for f in body["findings"] if f["source"] == "sqlite:spo2"]
    assert "SIMULATED" in spo2["detail"]


def test_spanish_transcript_gets_english_emergency_offline(ask) -> None:
    """hello -> sintoma -> Spanish chest pain + breathlessness: same card and urgency,
    English questions, action, steps and report, with Ollama and ChromaDB never called."""
    llm, retriever = Forbidden("llm"), Forbidden("retriever")
    hello = ask("hello", llm=llm, retriever=retriever)
    assert hello["clarifying_question"].startswith("Is your question about a symptom")
    symptom = ask("sintoma", hello, llm=FailingLLM(), retriever=retriever)
    assert symptom["clarifying_question"].startswith("What do you feel right now")
    body = ask("siento falta de aire y dolor en el pecho", symptom, llm=llm, retriever=retriever)
    assert body["urgency"] == "immediate" and body["protocol_id"] == "chest_pain"
    assert [r["rule_id"] for r in body["matched_rules"]][0] == "chest_pain.concerning_pattern"
    actionable(body)
    text = "\n".join([body["reply"], body["action"], body["report"]["text"],
                      *(s["text"] for s in body["steps"]), *body["notify"]])
    assert "Possible cardiac emergency" in body["action"]
    assert "MEDICAL CASE REPORT" in body["report"]["text"]
    assert not any(c in text for c in "áéíóúñ¿¡"), text
    assert 'text "falta de aire"' in body["report"]["text"]  # the astronaut's own words kept
    assert llm.calls == [] and retriever.calls == []


@pytest.mark.parametrize("message", ["I can't breathe", "sudden severe shortness of breath",
                                     "me falta mucho el aire"])
def test_severe_breathing_is_an_emergency_whatever_the_simulated_spo2(ask, message) -> None:
    llm, retriever = Forbidden("llm"), Forbidden("retriever")
    body = ask(message, llm=llm, retriever=retriever, readings=[SIM_SPO2])
    assert body["urgency"] == "immediate" and body["protocol_id"] == "breathing_difficulty"
    actionable(body)
    assert {s["who"] for s in body["steps"]} >= {"self", "crew", "equipment"}
    assert body["mission_procedures"][0]["title"] == "Mission respiratory emergency procedure"
    assert "SIMULATED" in body["report"]["text"] and "97" in body["report"]["text"]
    assert llm.calls == [] and retriever.calls == []


def test_simulated_reading_never_downgrades_the_alarm(ask) -> None:
    without = ask("I can't breathe", llm=Forbidden("llm"), retriever=Forbidden("retriever"))
    with_sim = ask("I can't breathe", llm=Forbidden("llm"), retriever=Forbidden("retriever"),
                   readings=[SIM_SPO2, SIM_HR])
    for key in ("urgency", "action", "steps", "matched_rules", "mission_procedures"):
        assert with_sim[key] == without[key], key


def test_missing_readings_are_stated_and_steps_still_given(ask) -> None:
    body = ask("shortness of breath", llm=FailingLLM(), retriever=FailingRetriever())
    actionable(body)
    report = body["report"]["text"]
    assert "SpO₂: no reading (value unknown)." in report
    assert "Pulse: no reading (value unknown)." in report
    assert {f["source"] for f in body["findings"] if f["kind"] == "data_gap"} >= {"sqlite:spo2", "sqlite:heart_rate"}


def test_readings_repository_down_on_an_alarm(ask) -> None:
    body = ask("I can't breathe", llm=Forbidden("llm"), retriever=Forbidden("retriever"),
               provider=FailingReadings())
    assert body["urgency"] == "immediate"
    actionable(body)
    assert "Readings unavailable" in body["report"]["text"]


def test_ollama_and_chromadb_down(ask) -> None:
    body = ask("shortness of breath", llm=FailingLLM(), retriever=FailingRetriever(),
               readings=[SIM_SPO2])
    actionable(body)
    assert body["urgency"] == "review_required"
    assert prompts.NOTICE_GUIDES_FAILED in body["data_notices"]


def test_negated_and_unknown_symptoms_keep_their_status(ask) -> None:
    body = ask("shortness of breath, no cough, not sure if I have a fever",
               llm=FailingLLM(), retriever=FailingRetriever())
    report = body["report"]["text"]
    assert "Cough: absent (denied)" in report
    assert "Fever: unknown (not known)" in report


def test_no_ground_link(db_path, clock) -> None:
    """Telemetry on, ground unreachable: the local answer and report are unchanged."""
    app = create_app(Settings(db_path=db_path, telemetry_enabled=True,
                              ground_api_url="http://127.0.0.1:9", telemetry_interval_seconds=0.05))
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as client:
        assert client.post("/astronauts", json={"id": "ana", "display_name": "Ana"}).status_code == 201
        body, *_ = post(client, db_path, {"astronaut_id": "ana", "message": "I can't breathe"},
                        llm=FailingLLM(), retriever=FailingRetriever(), readings=[SIM_SPO2])
    assert body["urgency"] == "immediate"
    actionable(body)
    assert "mission control (if the link is up)" in body["notify"]


def test_out_of_coverage_gives_actions_without_a_clinician(ask) -> None:
    body = ask("me duele el oído", llm=FailingLLM(), retriever=FailingRetriever())
    assert body["urgency"] == "review_required" and body["action"] == prompts.OUT_OF_COVERAGE_ACTION
    assert body["missing_guidance"] == [prompts.OUT_OF_COVERAGE_MISSING]
    assert body["report"]["transmission"] == "not_sent"
    no_clinician(body)


@pytest.mark.parametrize("draft", [
    "Se avisó a control de misión [1].",
    "Ya informé a la tripulación [1].",
    "No tienes fiebre, así que no es grave [1].",
    "Consulta al médico de a bordo [1].",
    "Esto descarta un problema respiratorio [1].",
])
def test_generated_explanation_cannot_claim_notification_absence_or_a_clinician(draft) -> None:
    assert not valid_draft(draft, [chunk(1)], "contexto")


def test_neutral_explanation_is_accepted() -> None:
    assert valid_draft("La falta de aire importa por su inicio y su intensidad [1].", [chunk(1)], "contexto")
