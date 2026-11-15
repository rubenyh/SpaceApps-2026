"""POST /assistant/messages end to end (plan §7): real router, real SQLite readings
(posted through POST /readings), injected events and fake LLM / retriever."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assistant.fakes import (
    FailingLLM,
    FailingReadings,
    FailingRetriever,
    FakeLLM,
    FakeRetriever,
    chunk,
)
from assistant.medical_cases import CASES, FRESH, FUTURE, STALE, _event, _reading
from onboard_api.assistant.state import AssistantDeps
from onboard_api.assistant.workflows.medical import prompts
from onboard_api.assistant.workflows.medical.context import (
    SqliteReadingsProvider,
    StaticEventSource,
)
from onboard_api.assistant.workflows.medical.protocols import load_catalog
from onboard_api.assistant.workflows.medical.triage import GENERIC_CLARIFYING_QUESTION
from onboard_api.dependencies import get_assistant_deps
from onboard_api.schemas.assistant import OperationalEvent

DRAFT = "Explicación breve basada en la guía local [1]."
CHUNKS = [chunk(1), chunk(2)]
_PERCENT = re.compile(r"\d+(?:[.,]\d+)?\s*%")
_TRANSMISSION = ("enviado", "transmitido", "se envió", "se transmitió")


class CountingReadings:
    """Real provider, with a call counter (alarms must not touch SQLite)."""

    def __init__(self, inner) -> None:
        self.inner, self.calls = inner, 0

    def load(self, astronaut_id, now):
        self.calls += 1
        return self.inner.load(astronaut_id, now)


def post(
    client: TestClient,
    db_path: Path,
    request: dict,
    *,
    events=(),
    readings=(),
    llm=None,
    retriever=None,
    provider=None,
):
    for body in readings:
        r = client.post("/readings", json=body)
        assert r.status_code == 201, r.text
    llm = llm or FakeLLM(DRAFT)
    retriever = retriever if retriever is not None else FakeRetriever(CHUNKS)
    counting = CountingReadings(provider or SqliteReadingsProvider(db_path))
    deps = AssistantDeps(
        llm=llm,
        retriever=retriever,
        readings=counting,
        events=StaticEventSource([OperationalEvent(**e) for e in events]),
    )
    client.app.dependency_overrides[get_assistant_deps] = lambda: deps
    r = client.post("/assistant/messages", json=request)
    assert r.status_code == 200, r.text
    body = r.json()
    check_invariants(body, retriever)
    return body, counting, llm, retriever


def _card_urls() -> dict[str, str | None]:
    return {
        f"{p.id}@{p.version}#{s.id}": s.url for p in load_catalog().values() for s in p.sources
    }


def check_invariants(body: dict, retriever) -> None:
    """Citations are cards or retrieved chunks; no probabilities; no transmission claims."""
    cards = _card_urls()
    retrieved = {
        c.chunk_id: c for call in getattr(retriever, "calls", []) for c in retriever.chunks[: call["k"]]
    }
    for s in body["sources"]:
        if s["kind"] == "protocol":
            assert s["id"] in cards, s
            assert s["url"] and s["url"] == cards[s["id"]], s
        else:
            assert s["id"] in retrieved, s
            assert s["url"] == retrieved[s["id"]].url
    causes = json.dumps(body["possible_causes"], ensure_ascii=False).lower()
    assert not _PERCENT.search(causes) and "probab" not in causes
    text = json.dumps(body, ensure_ascii=False).lower()
    assert not any(w in text for w in _TRANSMISSION), body
    if body["workflow"] == "medical":
        assert body["disclaimer"] == prompts.DISCLAIMER


def ids(body: dict) -> list[str]:
    return [body["protocol_id"], *body["additional_protocol_ids"]]


def kinds(body: dict) -> set[str]:
    return {s["kind"] for s in body["sources"]}


@pytest.fixture
def ask(client: TestClient, astronaut: str, db_path: Path):
    return lambda request, **kw: post(client, db_path, request, **kw)


# --- every synthetic case through the POST ---


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_case_through_post(ask, case: dict) -> None:
    body, readings, llm, retriever = ask(
        case["request"], events=case["events"], readings=case["readings"]
    )
    assert body["workflow"] == "medical"
    assert body["protocol_id"] == case["expect_protocol"]
    assert body["urgency"] == case["expect_urgency"]
    if case["expect_not_protocol"]:
        assert case["expect_not_protocol"] not in ids(body)

    route = case["expect_route"]
    assert body["needs_clarification"] is (route == "clarify")
    if route == "alarm":
        assert body["action"] and body["notify"]
        assert prompts.ALARM_NOTICE in body["data_notices"]
        assert kinds(body) == {"protocol"}
        assert readings.calls <= 1 and llm.calls == [] and retriever.calls == []
    elif route == "clarify":
        question = body["clarifying_question"]
        assert question and question.count("?") == 1 and question in body["reply"]
        assert llm.calls == [] and retriever.calls == []
    elif route == "assessment":
        assert body["action"]
        assert "protocol" in kinds(body)
        assert body["reply"].startswith(body["action"].split("\n")[0][:40])
    elif route == "educational":
        assert body["protocol_id"] is None and kinds(body) <= {"guide"}
    elif route == "out_of_coverage":
        assert body["action"] == prompts.OUT_OF_COVERAGE_ACTION
        assert body["sources"] == [] and body["possible_causes"] == []


def test_every_card_has_activating_and_near_case() -> None:
    for pid in load_catalog():
        assert any(c["expect_protocol"] == pid for c in CASES), pid
        assert any(c["expect_not_protocol"] == pid for c in CASES), pid


def test_unclear_asks_generic_question(ask) -> None:
    body, *_ = ask({"message": "No me siento bien", "astronaut_id": "ana"})
    assert body["clarifying_question"] == GENERIC_CLARIFYING_QUESTION
    assert body["reply"] == GENERIC_CLARIFYING_QUESTION
    assert body["urgency"] == "undetermined" and body["needs_clarification"]
    assert body["protocol_id"] is None and body["sources"] == []


# --- interpretation: negation, history, hypothesis ---


@pytest.mark.parametrize(
    "message",
    ["No me falta el aire", "Hace dos años me faltó el aire de repente", "¿Qué pasa si me falta el aire de repente?"],
    ids=["negated", "historical", "hypothetical"],
)
def test_breathing_not_active(ask, message: str) -> None:
    body, *_ = ask({"message": message, "astronaut_id": "ana"})
    assert body["urgency"] != "immediate"
    assert "breathing_difficulty" not in ids(body) or body["urgency"] == "informational"


def test_simultaneous_alarms(ask) -> None:
    body, *_ = ask({"message": "Mi compañero no responde y no respira bien", "astronaut_id": "ana"})
    assert body["protocol_id"] == "loss_of_consciousness_or_seizure"
    assert "breathing_difficulty" in body["additional_protocol_ids"]
    lines = [s for s in re.split(r"(?<=\.)\s+", body["action"]) if s]
    assert len(lines) == len(set(lines))  # actions deduplicated


# variant -> (readings, flags expected on the SpO2 finding). "unavailable" breaks the repository.
EVIDENCE_VARIANTS = {
    "fresh": ([_reading("spo2", 97, "%")], []),
    "simulated": ([_reading("spo2", 97, "%", source="simulated:pulse-ox")], ["simulated"]),
    "demo": ([_reading("spo2", 97, "%", source="demo")], ["simulated"]),
    "stale": ([_reading("spo2", 97, "%", recorded_at=STALE)], ["stale"]),
    "future": ([_reading("spo2", 97, "%", recorded_at=FUTURE)], ["stale"]),
    "suspect": ([_reading("spo2", 97, "%", quality="suspect")], ["poor_quality"]),
    "simulated_stale_bad": ([_reading("spo2", 97, "%", recorded_at=STALE, quality="bad",
                                      source="simulated:pulse-ox")], ["simulated", "stale", "poor_quality"]),
    "missing": ([], ["missing"]),
    "unavailable": ([], ["missing"]),
}
EVIDENCE_PATHS = {  # message -> (protocol, urgency): flags are the same on the alarm and review paths
    "Me falta mucho el aire de repente": ("breathing_difficulty", "immediate"),
    "Tengo fiebre y tos desde ayer": ("fever_or_respiratory_illness", "review_required"),
}


@pytest.mark.parametrize("message", EVIDENCE_PATHS, ids=["immediate", "review"])
@pytest.mark.parametrize("variant", EVIDENCE_VARIANTS)
def test_evidence_flags_on_reading_findings(ask, tmp_path: Path, message: str, variant: str) -> None:
    """Flags label the evidence; they never change the card or urgency (severe breathing
    with SpO2 97 % stays immediate whatever the reading)."""
    readings, flags = EVIDENCE_VARIANTS[variant]
    provider = SqliteReadingsProvider(tmp_path) if variant == "unavailable" else None
    body, *_ = ask({"message": message, "astronaut_id": "ana"}, readings=readings, provider=provider)
    assert (body["protocol_id"], body["urgency"]) == EVIDENCE_PATHS[message]
    source = "sqlite" if variant == "unavailable" else "sqlite:spo2"
    [spo2] = [f for f in body["findings"] if f["source"] == source]
    assert spo2["evidence_flags"] == flags
    assert spo2["kind"] == ("data_gap" if "missing" in flags else "reading")
    assert all(f["evidence_flags"] == [] for f in body["findings"] if not f["source"].startswith("sqlite"))


def test_resolved_sudden_weakness_is_alarm(ask) -> None:
    body, *_ = ask(
        {"message": "Tuve debilidad repentina en un lado del cuerpo, ya se me pasó", "astronaut_id": "ana"}
    )
    assert body["urgency"] == "immediate" and body["protocol_id"] == "neurologic_red_flags"
    assert any("already eased" in f["detail"] for f in body["findings"])


def test_dizziness_adaptation_vs_speech_change(ask) -> None:
    calm, *_ = ask({"message": "Estoy mareado en los primeros días de adaptación", "astronaut_id": "ana"})
    assert calm["protocol_id"] == "dizziness_or_space_motion_sickness"
    assert calm["urgency"] == "review_required" and "neurologic_red_flags" not in ids(calm)
    alarm, *_ = ask({"message": "Estoy mareado y se me traba el habla", "astronaut_id": "ana"})
    assert alarm["protocol_id"] == "neurologic_red_flags" and alarm["urgency"] == "immediate"


def test_urinary_scenarios(ask) -> None:
    flank, *_ = ask({"message": "Tengo fiebre y dolor en el costado", "astronaut_id": "ana"})
    assert flank["protocol_id"] == "urinary_symptoms" and flank["urgency"] == "review_required"
    retention, *_ = ask({"message": "De repente no puedo orinar", "astronaut_id": "ana"})
    assert retention["protocol_id"] == "urinary_symptoms" and retention["urgency"] == "immediate"


def test_muscle_pain_cola_urine(ask) -> None:
    body, *_ = ask(
        {"message": "Tras el ejercicio intenso tengo dolor muscular y orina color cola", "astronaut_id": "ana"}
    )
    assert body["protocol_id"] == "muscle_symptoms" and body["urgency"] == "review_required"
    assert any(c["id"] for c in body["possible_causes"])  # traceable card candidate


def test_isolated_rgb_has_no_clinical_cause(ask) -> None:
    body, *_ = ask(
        {"message": "La muestra de orina salió de color rojizo pero no tengo síntomas", "astronaut_id": "ana"},
        readings=[_reading("urine_color", unit="rgb_hex", value_text="#B04030")],
    )
    assert body["possible_causes"] == [] and body["urgency"] != "immediate"


# --- events ---


def test_confirmed_dosimetry_event(ask) -> None:
    ev = _event("radiation", origin="dosimeter:area-2")
    body, *_ = ask({"message": "¿Qué hago?", "astronaut_id": "ana"}, events=[ev])
    assert body["protocol_id"] == "radiation_alert" and body["urgency"] == "immediate"
    event = [f for f in body["findings"] if f["source"] == f"event:{ev['id']}"]
    assert event and "CONFIRMED" in event[0]["detail"] and "dosimeter:area-2" in event[0]["detail"]


def test_simulated_event_is_labelled(ask) -> None:
    ev = _event("radiation", provenance="simulated", origin="dosimeter:drill")
    body, *_ = ask({"message": "¿Qué hago?", "astronaut_id": "ana"}, events=[ev])
    assert body["urgency"] == "immediate" and "SIMULATED" in body["action"]
    assert any("SIMULATED" in f["detail"] for f in body["findings"])
    assert not any("CONFIRMED" in f["detail"] for f in body["findings"])


def test_radiation_question_with_urine_only(ask) -> None:
    body, *_ = ask(
        {"message": "¿Estuve expuesto a radiación? Solo tengo los datos de orina", "astronaut_id": "ana"},
        readings=[_reading("urine_radiation_marker", 0.4, "a.u.")],
    )
    assert body["protocol_id"] == "radiation_alert" and body["urgency"] != "immediate"
    gaps = [f["detail"].lower() for f in body["findings"] if f["kind"] == "data_gap"]
    assert any("dosimetr" in g for g in gaps)
    assert all(c["status"] != "compatible" for c in body["possible_causes"])


# --- reading quality ---


def test_stale_suspect_and_missing_readings(ask) -> None:
    body, *_ = ask(
        {"message": "Tengo fiebre y tos desde ayer", "astronaut_id": "ana"},
        readings=[
            _reading("heart_rate", 80, "bpm", recorded_at=STALE),
            _reading("spo2", 91, "%", quality="suspect", recorded_at=FRESH),
        ],
    )
    notices = " ".join(body["data_notices"])
    assert "min old" in notices and "doubtful" in notices

    body, *_ = ask({"message": "Tengo fiebre y tos desde ayer", "astronaut_id": "ana"})
    # The stale/suspect rows above persist; a new astronaut has none.
    body, *_ = ask({"message": "Tengo fiebre y tos desde ayer", "astronaut_id": None})
    assert any("no readings were checked" in n for n in body["data_notices"])


def test_missing_readings(ask) -> None:
    body, *_ = ask({"message": "Tengo fiebre y tos desde ayer", "astronaut_id": "ana"})
    assert "No SpO₂ reading." in body["data_notices"]
    assert "No pulse reading." in body["data_notices"]


@pytest.mark.parametrize("broken", ["directory", "raises"])
def test_repository_unavailable(ask, tmp_path: Path, broken: str) -> None:
    provider = SqliteReadingsProvider(tmp_path) if broken == "directory" else FailingReadings()
    body, *_ = ask({"message": "Tengo fiebre y tos desde ayer", "astronaut_id": "ana"}, provider=provider)
    assert body["protocol_id"] == "fever_or_respiratory_illness" and body["action"]
    assert prompts.NOTICE_READINGS_FAILED in body["data_notices"]


# --- retrieval and Ollama failures ---


def test_empty_retrieval_assessment(ask) -> None:
    body, _, llm, _ = ask({"message": "Tengo fiebre y tos desde ayer", "astronaut_id": "ana"}, retriever=FakeRetriever([]))
    assert prompts.NOTICE_NO_GUIDES in body["data_notices"]
    assert kinds(body) == {"protocol"} and body["action"] and llm.calls == []


def test_educational_with_guides(ask) -> None:
    body, _, llm, retriever = ask({"message": "¿Qué es la cinetosis espacial?", "astronaut_id": "ana"})
    assert body["urgency"] == "informational" and body["protocol_id"] is None
    assert body["sources"] and kinds(body) == {"guide"}
    card = load_catalog()["dizziness_or_space_motion_sickness"]
    assert retriever.calls[0]["query"] == card.title  # topic, never the raw message
    assert "cinetosis espacial?" not in llm.calls[0][1]


@pytest.mark.parametrize("retriever", [FakeRetriever([]), FailingRetriever()], ids=["empty", "failing"])
def test_educational_abstains_without_chunks(ask, retriever) -> None:
    body, *_ = ask({"message": "¿Qué es la cinetosis espacial?", "astronaut_id": "ana"}, retriever=retriever)
    assert body["reply"] == prompts.EDUCATIONAL_ABSTAIN and body["sources"] == []


def test_ollama_failing_falls_back_to_card(ask) -> None:
    body, *_ = ask({"message": "Tengo fiebre y tos desde ayer", "astronaut_id": "ana"}, llm=FailingLLM())
    assert prompts.NOTICE_LLM_FAILED in body["data_notices"]
    assert body["action"] and body["reply"].startswith(body["action"].split("\n")[0][:40])
    assert kinds(body) == {"protocol"}


@pytest.mark.parametrize(
    "message, urgency",
    [("Siento presión en el pecho desde hace un rato y sudor frío", "immediate"),
     ("Me duele el pecho", "review_required")],
    ids=["immediate", "review"],
)
def test_ollama_down_states_missing_mission_guidance(ask, message: str, urgency: str) -> None:
    """With Ollama down, the card still answers and says which mission guidance it lacks."""
    body, *_ = ask({"message": message, "astronaut_id": "ana"}, llm=FailingLLM())
    assert body["protocol_id"] == "chest_pain" and body["urgency"] == urgency and body["action"]
    assert body["missing_guidance"] and body["mission_procedures"]
    assert not any(p["loaded"] for p in body["mission_procedures"])
    report = body["report"]["text"]
    assert "NOT loaded in the assistant" in report
    assert all(m in report for m in body["missing_guidance"])


def test_all_dependencies_down_alarm_still_immediate(ask) -> None:
    body, *_ = ask(
        {"message": "Mi compañero no responde", "astronaut_id": "ana"},
        llm=FailingLLM(),
        retriever=FailingRetriever(),
        provider=FailingReadings(),
    )
    assert body["urgency"] == "immediate" and body["action"]
    assert body["protocol_id"] == "loss_of_consciousness_or_seizure"


# --- clarification round-trip (stateless: resend the report plus the new data) ---

HEADACHE_FOLLOW_UPS = {
    "text": {"message": "Me duele la cabeza. Empezó poco a poco y es leve; no tengo problemas del habla ni de visión."},
    "structured": {
        "message": "Me duele la cabeza",
        "reported_symptoms": [
            {"symptom": "headache", "onset": "gradual", "severity": "mild"},
            {"symptom": "speech_change", "status": "absent"},
            {"symptom": "vision_loss", "status": "absent"},
        ],
    },
}


@pytest.mark.parametrize("answer", HEADACHE_FOLLOW_UPS, ids=list(HEADACHE_FOLLOW_UPS))
def test_headache_clarification_round_trip(ask, answer: str) -> None:
    first, *_ = ask({"message": "Me duele la cabeza", "astronaut_id": "ana"})
    assert first["needs_clarification"] and first["urgency"] == "undetermined"
    question = first["clarifying_question"]

    body, *_ = ask({**HEADACHE_FOLLOW_UPS[answer], "astronaut_id": "ana"})
    assert not body["needs_clarification"] and body["clarifying_question"] != question
    assert body["urgency"] == "review_required"  # plan card 4: mild headache goes to review, no alarm
