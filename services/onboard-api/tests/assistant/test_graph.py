"""Graph-level tests with fakes. Triage is stubbed where the rules are not under test."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from fakes import (
    FailingLLM,
    FailingReadings,
    FailingRetriever,
    FakeEvents,
    FakeLLM,
    FakeReadings,
    FakeRetriever,
    Forbidden,
    chunk,
)
from onboard_api.assistant import routing
from onboard_api.assistant.graph import build_assistant_graph, respond
from onboard_api.assistant.state import AssistantDeps
from onboard_api.assistant.workflows.medical import nodes, prompts
from onboard_api.assistant.workflows.medical.context import (
    SqliteReadingsProvider,
    load_events_file,
)
from onboard_api.assistant.workflows.medical.state import (
    Decision,
    Interpretation,
    Protocol,
    ProtocolAction,
    ProtocolSource,
    ReadingsContext,
    RuleHit,
)
from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.database import connect, init_db
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.schemas.assistant import (
    AssistantRequest,
    Finding,
    GuideSource,
    MatchedRule,
    OperationalEvent,
    ReportedSymptom,
)
from onboard_api.schemas.astronauts import AstronautCreate
from onboard_api.schemas.readings import ReadingCreate
from onboard_api.services.assistant import DISCLAIMER

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
ACTION = "Pide una valoración al responsable médico a bordo."
CARD = Protocol(
    id="breathing_difficulty",
    version="1",
    title="Dificultad respiratoria",
    priority=20,
    summary="Resumen conservado de la ficha.",
    actions={"review": ProtocolAction(urgency="review_required", text=ACTION)},
    sources=[ProtocolSource(id="s1", title="MedlinePlus", section="Resumen", url="https://x")],
    guide_topics=["breathing_problems", "pulse_oximetry"],
)
CARD_SOURCE = GuideSource(id="breathing_difficulty@1#s1", title="MedlinePlus", kind="protocol")


def hit(urgency="review_required") -> RuleHit:
    return RuleHit(rule_id="breathing_difficulty.r", protocol_id=CARD.id, urgency=urgency, action_key="review")


def decision(urgency="review_required", question=None) -> Decision:
    return Decision(
        urgency=urgency,
        protocol_id=CARD.id,
        additional_protocol_ids=[],
        action=ACTION,
        notify=["responsable médico a bordo"],
        matched_rules=[MatchedRule(rule_id="breathing_difficulty.r", protocol_id=CARD.id, protocol_version="1", urgency=urgency)],
        findings=[Finding(kind="symptom", detail="Falta de aire reportada", source="report")],
        possible_causes=[],
        clarifying_question=question,
        protocol_sources=[CARD_SOURCE],
        summary=f"{ACTION}\n\n{CARD.summary}",
    )


@dataclass
class Triage:
    interp: Interpretation = field(
        default_factory=lambda: Interpretation(observations=(), request_kind="report", medical_signal=True)
    )
    alarm_hits: list = field(default_factory=list)
    case_hits: list = field(default_factory=list)
    route: str = "out_of_coverage"
    decision: Decision | None = None


@pytest.fixture
def triage(monkeypatch) -> Triage:
    t = Triage()
    monkeypatch.setattr(nodes, "interpret", lambda request: t.interp)
    monkeypatch.setattr(routing, "interpret", lambda request: t.interp)
    monkeypatch.setattr(nodes, "evaluate_alarms", lambda interp, events, aid: t.alarm_hits)
    monkeypatch.setattr(nodes, "evaluate_case", lambda interp, events, readings: t.case_hits)
    monkeypatch.setattr(nodes, "select_route", lambda interp, alarms, cases: t.route)
    monkeypatch.setattr(nodes, "decide", lambda hits, catalog, readings: t.decision)
    monkeypatch.setattr(nodes, "load_catalog", lambda: {CARD.id: CARD})
    return t


def ask(deps: AssistantDeps, message="Me falta el aire", **kw):
    request = AssistantRequest(message=message, astronaut_id="ana", **kw)
    return respond(build_assistant_graph(deps), request, NOW)


def deps(llm=None, retriever=None, readings=None, events=None) -> AssistantDeps:
    return AssistantDeps(
        llm=llm or Forbidden("llm"),
        retriever=retriever or Forbidden("retriever"),
        readings=readings or FakeReadings(),
        events=events or FakeEvents(),
    )


def assert_medical(r) -> None:
    assert r.workflow == "medical"
    assert r.disclaimer == DISCLAIMER


# --- Alarm branch ---


def test_alarm_never_calls_readings_retriever_or_llm(triage: Triage) -> None:
    triage.alarm_hits = [hit("immediate")]
    triage.decision = decision("immediate")
    llm, retriever, readings = Forbidden("llm"), Forbidden("retriever"), Forbidden("readings")
    r = ask(AssistantDeps(llm, retriever, readings, FakeEvents()))
    assert_medical(r)
    assert r.urgency == "immediate"
    assert r.reply == triage.decision.summary
    assert r.sources == [CARD_SOURCE]
    assert r.protocol_id == CARD.id
    assert prompts.ALARM_NOTICE in r.data_notices
    assert llm.calls == retriever.calls == readings.calls == []


def test_real_rules_alarm_with_all_dependencies_failing() -> None:
    """Unstubbed triage: a severe sudden breathing problem is immediate even when
    every dependency is down."""
    r = ask(
        AssistantDeps(FailingLLM(), FailingRetriever(), FailingReadings(), FakeEvents()),
        message="Me falta el aire",
        reported_symptoms=[
            ReportedSymptom(symptom="shortness_of_breath", onset="sudden", severity="severe")
        ],
    )
    assert_medical(r)
    assert r.urgency == "immediate"
    assert r.action and r.reply.startswith(r.action)
    assert all(s.kind == "protocol" for s in r.sources)


# --- Assessment / educational ---


def test_assessment_with_valid_draft(triage: Triage) -> None:
    triage.case_hits, triage.route, triage.decision = [hit()], "assessment", decision()
    llm = FakeLLM("La falta de aire puede tener varios orígenes [1]; la guía lo describe [2].")
    retriever = FakeRetriever([chunk(1), chunk(2)])
    readings = FakeReadings(ReadingsContext(available=True, warnings=["Sin lectura de SpO₂."]))
    r = ask(deps(llm, retriever, readings))
    assert_medical(r)
    assert r.reply.startswith(ACTION + "\n\n")
    assert "[1]" in r.reply
    assert [s.id for s in r.sources] == [CARD_SOURCE.id, "chunk-1", "chunk-2"]
    assert r.sources[1].kind == "guide" and r.sources[1].url
    assert "Sin lectura de SpO₂." in r.data_notices
    assert retriever.calls == [
        {"query": CARD.title, "k": 3, "topics": CARD.guide_topics, "language": "es"}
    ]
    system, user = llm.calls[0]
    assert "español" in system
    assert "[2] Problemas respiratorios" in user and "Falta de aire reportada" in user
    assert "Sin lectura de SpO₂." in user and ACTION in user
    assert readings.calls == ["ana"]


def test_ollama_failure_falls_back_to_card_text(triage: Triage) -> None:
    triage.case_hits, triage.route, triage.decision = [hit()], "assessment", decision()
    r = ask(deps(FailingLLM(), FakeRetriever([chunk(1)])))
    assert_medical(r)
    assert r.reply == triage.decision.summary
    assert r.sources == [CARD_SOURCE]
    assert prompts.NOTICE_LLM_FAILED in r.data_notices


@pytest.mark.parametrize(
    "draft",
    ["Según la guía [3], conviene valorarlo.", "Tu pulso de 140 es preocupante [1].", "   "],
    ids=["citation-out-of-range", "invented-number", "empty"],
)
def test_invalid_draft_is_dropped(triage: Triage, draft: str) -> None:
    triage.case_hits, triage.route, triage.decision = [hit()], "assessment", decision()
    r = ask(deps(FakeLLM(draft), FakeRetriever([chunk(1), chunk(2)])))
    assert r.reply == triage.decision.summary
    assert r.sources == [CARD_SOURCE]
    assert prompts.NOTICE_DRAFT_REJECTED in r.data_notices


def test_assessment_without_guides_skips_llm(triage: Triage) -> None:
    triage.case_hits, triage.route, triage.decision = [hit()], "assessment", decision()
    llm = Forbidden("llm")
    r = ask(deps(llm, FailingRetriever(), FailingReadings()))
    assert r.reply == triage.decision.summary
    assert prompts.NOTICE_GUIDES_FAILED in r.data_notices
    assert prompts.NOTICE_READINGS_FAILED in r.data_notices
    assert llm.calls == []


@pytest.mark.parametrize("retriever", [FakeRetriever([]), FailingRetriever()], ids=["empty", "down"])
def test_educational_without_chunks_abstains(triage: Triage, retriever) -> None:
    triage.interp = Interpretation((), "educational", True, topic_hint=CARD.id)
    triage.route = "educational"
    llm = Forbidden("llm")
    r = ask(deps(llm, retriever), message="¿Qué es la oximetría?")
    assert_medical(r)
    assert r.reply == prompts.EDUCATIONAL_ABSTAIN
    assert r.urgency == "informational"
    assert r.sources == [] and r.protocol_id is None
    assert {prompts.NOTICE_NO_GUIDES, prompts.NOTICE_GUIDES_FAILED} & set(r.data_notices)
    assert llm.calls == []


def test_educational_llm_down_returns_excerpt(triage: Triage) -> None:
    triage.interp = Interpretation((), "educational", True, topic_hint=CARD.id)
    triage.route = "educational"
    retriever = FakeRetriever([chunk(1), chunk(2)])
    r = ask(deps(FailingLLM(), retriever), message="¿Qué es la oximetría?")
    assert r.urgency == "informational"
    assert "Texto de la guía número 1." in r.reply
    assert [s.id for s in r.sources] == ["chunk-1"]
    assert retriever.calls[0]["query"] == "¿Qué es la oximetría?"
    assert retriever.calls[0]["topics"] == CARD.guide_topics


def test_medical_clarify_asks_one_question(triage: Triage) -> None:
    q = "¿La falta de aire empezó de repente?"
    triage.case_hits, triage.route = [hit("undetermined")], "clarify"
    triage.decision = decision("undetermined", question=q)
    r = ask(deps())
    assert_medical(r)
    assert r.needs_clarification and r.clarifying_question == q
    assert r.reply.endswith(q)


def test_out_of_coverage(triage: Triage) -> None:
    triage.route = "out_of_coverage"
    r = ask(deps(), message="Me duele el codo")
    assert_medical(r)
    assert r.urgency == "review_required"
    assert r.protocol_id is None
    assert r.action == prompts.OUT_OF_COVERAGE_ACTION
    assert r.reply.startswith(prompts.OUT_OF_COVERAGE_ACTION)


# --- Parent routing ---


def no_signal(triage: Triage) -> None:
    triage.interp = Interpretation((), "unclear", False)


@pytest.mark.parametrize(
    "message",
    ["¿Cuál es la capital de Francia hoy?", "Necesito apoyo psicológico, me siento triste y con ansiedad"],
    ids=["off-topic", "psych"],
)
def test_unsupported(triage: Triage, message: str) -> None:
    no_signal(triage)
    readings = Forbidden("readings")
    r = ask(deps(readings=readings), message=message)
    assert r.workflow == "unsupported" and not r.needs_clarification
    assert r.reply == routing.UNSUPPORTED_REPLY
    assert readings.calls == []


def test_psych_message_with_medical_signal_still_unsupported(triage: Triage) -> None:
    triage.interp = Interpretation((), "unclear", True)
    r = ask(deps(), message="Tengo mucha ansiedad")
    assert r.workflow == "unsupported"


def test_unsupported_distress_adds_emergency_line(triage: Triage) -> None:
    no_signal(triage)
    r = ask(deps(), message="Es una emergencia, no puedo más con esto")
    assert r.workflow == "unsupported"
    assert routing.EMERGENCY_LINE in r.reply


def test_vague_message_clarifies(triage: Triage) -> None:
    no_signal(triage)
    readings = Forbidden("readings")
    r = ask(deps(readings=readings), message="Hola")
    assert r.workflow == "clarify" and r.needs_clarification
    assert r.reply.count("?") == 1 and r.clarifying_question == r.reply
    assert readings.calls == []


def event(**kw) -> OperationalEvent:
    data = {
        "id": "co2-1", "type": "cabin_co2", "origin": "ship:eclss", "occurred_at": NOW - timedelta(minutes=1),
        "status": "active", "provenance": "confirmed", "astronaut_ids": [],
    }
    return OperationalEvent(**{**data, **kw})


def test_active_event_routes_to_medical(triage: Triage) -> None:
    no_signal(triage)
    triage.alarm_hits, triage.decision = [hit("immediate")], decision("immediate")
    r = ask(deps(events=FakeEvents([event()])), message="Hola")
    assert r.workflow == "medical" and r.urgency == "immediate"


@pytest.mark.parametrize(
    "ev", [event(astronaut_ids=["luis"]), event(status="resolved")], ids=["other-astronaut", "resolved"]
)
def test_irrelevant_event_does_not_route(triage: Triage, ev: OperationalEvent) -> None:
    no_signal(triage)
    assert ask(deps(events=FakeEvents([ev])), message="Hola").workflow == "clarify"


def test_graph_compiled_once_per_deps() -> None:
    d = deps()
    assert build_assistant_graph(d) is build_assistant_graph(d)


# --- Readings provider and demo events ---


def test_sqlite_readings_provider(tmp_path) -> None:
    db = tmp_path / "onboard.db"
    provider = SqliteReadingsProvider(db)
    assert provider.load("ana", NOW).available is False  # no DB file

    init_db(db, NOW)
    conn = connect(db)
    AstronautRepository(conn).create(AstronautCreate(id="ana", display_name="Ana"), NOW)
    repo = ReadingRepository(conn)
    repo.create(
        ReadingCreate(astronaut_id="ana", kind="spo2", value=91, unit="%", quality="suspect",
                      recorded_at=NOW - timedelta(minutes=42), source="serial:pulse"),
        NOW,
    )
    repo.create(
        ReadingCreate(astronaut_id="ana", kind="muscle_density", value=1.0, unit="raw",
                      quality="good", recorded_at=NOW, source="serial:muscle"),
        NOW,
    )
    conn.close()

    ctx = provider.load("ana", NOW)
    assert ctx.available
    spo2 = ctx.latest["spo2"]
    assert spo2.stale and spo2.age_seconds == 42 * 60 and spo2.quality == "suspect"
    text = " ".join(ctx.warnings)
    assert "Sin lectura de pulso" in text
    assert "SpO₂ tiene 42 min" in text
    assert "calidad dudosa" in text
    assert "método y unidad pendientes" in text

    unknown = provider.load("nadie", NOW)
    assert not unknown.available and "no registrado" in unknown.warnings[0]
    assert not provider.load(None, NOW).available


def test_demo_events_fixture_loads() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "demo" / "events.example.json"
    events = load_events_file(path)
    assert {(e.type, e.provenance) for e in events} == {("radiation", "simulated"), ("cabin_co2", "confirmed")}
