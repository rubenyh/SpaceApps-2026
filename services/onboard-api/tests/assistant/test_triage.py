"""Unit tests of interpret, triage rules and decide (no graph, no I/O)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from conftest import T0
from medical_cases import CASES
from onboard_api.assistant.workflows.medical.interpret import interpret
from onboard_api.assistant.workflows.medical import protocols
from onboard_api.assistant.workflows.medical.protocols import load_catalog
from onboard_api.assistant.workflows.medical.state import ReadingsContext, VitalReading
from onboard_api.assistant.workflows.medical.triage import (
    GENERIC_CLARIFYING_QUESTION,
    decide,
    evaluate_alarms,
    evaluate_case,
    select_route,
)
from onboard_api.schemas.assistant import AssistantRequest, OperationalEvent

CATALOG = load_catalog()
STALE_AFTER = {"heart_rate": 300, "spo2": 300, "muscle_density": 604800}  # urine_*: 86400


def obs(message: str, **extra):
    interp = interpret(AssistantRequest(message=message, astronaut_id="ana", **extra))
    return interp, {o.symptom: o for o in interp.observations}


def readings_ctx(rows: list[dict]) -> ReadingsContext:
    ctx = ReadingsContext(available=True)
    for r in rows:
        at = datetime.fromisoformat(r["recorded_at"])
        age = int((T0 - at).total_seconds())
        ctx.latest[r["kind"]] = VitalReading(
            kind=r["kind"], value=r.get("value"), value_text=r.get("value_text"), unit=r["unit"],
            recorded_at=at, quality=r["quality"], source=r["source"], age_seconds=age,
            stale=age > STALE_AFTER.get(r["kind"], 86400), id=r.get("id", 0),
        )
    return ctx


def run(request: dict, events: list[dict] = (), readings: list[dict] = ()):
    """Same order as the graph: alarms first (no readings), then the case."""
    interp = interpret(AssistantRequest(**request))
    evs = [OperationalEvent(**e) for e in events]
    alarms = evaluate_alarms(interp, evs, request.get("astronaut_id"))
    if alarms:
        return "alarm", decide(alarms, CATALOG, None)
    ctx = readings_ctx(list(readings))
    hits = evaluate_case(interp, evs, ctx)
    route = select_route(interp, alarms, hits)
    return route, decide(hits, CATALOG, ctx) if hits else None


# --- cards ---


def test_catalog_has_16_versioned_cards():
    plan = Path(__file__).parents[4] / "docs" / "plan-agente-medico-space-apps.md"
    text = plan.read_text(encoding="utf-8")
    assert len(CATALOG) == 16
    for card in CATALOG.values():
        assert card.version == "2.1.0"
        assert "Informational support" in card.summary
        assert card.guide_topics
        for source in card.sources:
            assert source.url in text, (card.id, source.url)
        for cand in card.candidates:
            assert set(cand.source_ids) <= {s.id for s in card.sources}
        for question in card.questions.values():
            assert question.endswith("?") or "? " in question
    assert CATALOG["loss_of_consciousness_or_seizure"].priority < CATALOG["breathing_difficulty"].priority
    raw = json.loads((Path(protocols.__file__).parent / "muscle_symptoms.json").read_text("utf-8"))
    assert raw["actions"]["suspected_rhabdo"]["urgency"] == "review_required"
    assert "stop exertion" in raw["actions"]["suspected_rhabdo"]["text"]
    assert any("creatine kinase" in m for m in raw["actions"]["suspected_rhabdo"]["missing_guidance"])


def test_cards_give_cited_steps_without_an_onboard_clinician():
    """v2: no clinician on board. Every action has cited steps; emergencies name a procedure."""
    for card in CATALOG.values():
        raw = (Path(protocols.__file__).parent / f"{card.id}.json").read_text("utf-8").lower()
        assert "responsable médico" not in raw and "médico a bordo" not in raw, card.id
        ids = {s.id for s in card.sources}
        for key, action in card.actions.items():
            assert action.steps, (card.id, key)
            for step in action.steps:
                assert set(step.source_ids) <= ids, (card.id, key, step.source_ids)
            if action.urgency == "immediate":
                assert action.mission_procedure, (card.id, key)
    # The alone astronaut gets something to do for breathing without anyone else.
    br = CATALOG["breathing_difficulty"].actions
    assert any(s.who == "self" for s in br["new_no_red_flags"].steps)
    assert {s.who for s in br["immediate"].steps} >= {"self", "crew", "equipment"}


# --- interpret ---


def test_negation_is_clause_level():
    _, o = obs("No me falta el aire, pero tengo dolor de pecho")
    assert o["shortness_of_breath"].status == "absent"
    assert o["chest_pain"].status == "present"
    _, o = obs("Sin fiebre ni tos")
    assert o["fever"].status == "absent" and o["cough"].status == "absent"


def test_patterns_with_no_are_present():
    _, o = obs("No puedo orinar")
    assert o["unable_to_urinate"].status == "present"
    _, o = obs("Pedro no responde")
    assert o["unresponsive"].status == "present"
    assert o["unresponsive"].subject == "other"


def test_unknown_and_neutral_no():
    _, o = obs("No sé si tengo fiebre")
    assert o["fever"].status == "unknown"
    _, o = obs("No se me quita el dolor de cabeza")
    assert o["headache"].status == "present"
    assert o["headache"].persistence == "ongoing"


def test_hypothetical_historical_resolved():
    interp, o = obs("¿Qué hago si me falta el aire?")
    assert o["shortness_of_breath"].temporality == "hypothetical"
    assert interp.request_kind == "educational"
    _, o = obs("Hace dos años me desmayé, pero ahora tengo tos")
    assert o["fainting"].temporality == "historical"
    assert o["cough"].temporality == "current"
    _, o = obs("El año pasado tuve dolor de pecho")
    assert o["chest_pain"].temporality == "historical"
    _, o = obs("Tuve debilidad en un brazo. Ya se me pasó.")
    assert o["one_sided_weakness"].temporality == "resolved"
    _, o = obs("Se me trabó el habla, duró unos minutos y pasó")
    assert o["speech_change"].temporality == "resolved"


def test_subject_onset_severity():
    _, o = obs("Mi compañero tiene dolor de pecho muy fuerte que empezó de repente")
    cp = o["chest_pain"]
    assert (cp.subject, cp.severity, cp.onset) == ("other", "severe", "sudden")
    _, o = obs("Tengo tos", reported_by="luis")
    assert o["cough"].subject == "other"


def test_accent_insensitive():
    _, a = obs("Vomité sangre")
    _, b = obs("vomite sangre")
    assert a.keys() == b.keys() and "vomiting_blood" in a


def test_structured_overrides_text():
    interp, o = obs("Tengo tos", reported_symptoms=[{"symptom": "cough", "severity": "severe"}])
    assert (o["cough"].origin, o["cough"].severity) == ("structured", "severe")
    interp, o = obs("No me falta el aire", reported_symptoms=[{"symptom": "shortness_of_breath"}])
    assert o["shortness_of_breath"].status == "present"
    interp, o = obs("Tengo un problema",
                    reported_symptoms=[{"symptom": "speech_change", "persistence": "resolved"}])
    assert o["speech_change"].temporality == "resolved"
    assert evaluate_alarms(interp, [], "ana")[0].protocol_id == "neurologic_red_flags"


def test_review_1_educational_marker_is_clause_scoped():
    interp, o = obs("No sé qué es, me duele el pecho y me falta el aire")
    assert o["chest_pain"].temporality == o["shortness_of_breath"].temporality == "current"
    assert interp.request_kind == "report"
    assert [h.protocol_id for h in evaluate_alarms(interp, [], "ana")] == ["chest_pain"]
    _, o = obs("¿Qué hago si me falta el aire y tengo dolor de pecho?")
    assert o["shortness_of_breath"].temporality == o["chest_pain"].temporality == "hypothetical"


def test_review_2_resolved_is_segment_scoped_and_severe_sob_alarms_when_resolved():
    interp, o = obs("Ya estoy bien, pero me falta el aire mucho")
    assert o["shortness_of_breath"].temporality == "current"
    assert evaluate_alarms(interp, [], "ana")[0].rule_id == "breathing_difficulty.severe_or_sudden"
    _, o = obs("Me desmayé hace un rato, pero ya estoy bien")
    assert o["fainting"].temporality == "resolved"
    interp, o = obs("De repente me faltó el aire, ya se me pasó")
    assert o["shortness_of_breath"].temporality == "resolved"
    assert evaluate_alarms(interp, [], "ana")[0].rule_id == "breathing_difficulty.severe_or_sudden"


def test_review_3_sin_embargo_is_not_a_negator():
    interp, o = obs("Sin embargo me duele mucho el pecho")
    assert o["chest_pain"].status == "present"
    assert evaluate_alarms(interp, [], "ana")[0].protocol_id == "chest_pain"
    _, o = obs("Sin duda tengo fiebre")
    assert o["fever"].status == "present"


def test_review_4_resolved_chest_pressure_still_alarms():
    interp, o = obs("Ya se me pasó la presión en el pecho")
    assert o["chest_pain"].temporality == "resolved"
    assert evaluate_alarms(interp, [], "ana")[0].rule_id == "chest_pain.concerning_pattern"
    route, _ = run({"message": "Tuve un dolor de pecho leve, ya se me pasó", "astronaut_id": "ana"})
    assert route == "assessment"  # resolved, no concerning pattern: review, not alarm


def test_review_5_hace_tiempo_que_is_ongoing():
    _, o = obs("Hace tiempo que me falta el aire")
    sob = o["shortness_of_breath"]
    assert (sob.temporality, sob.persistence) == ("current", "ongoing")
    _, o = obs("Hace una semana que tengo tos")
    assert o["cough"].temporality == "current"
    _, o = obs("Hace mucho tiempo tuve dolor de pecho")
    assert o["chest_pain"].temporality == "historical"
    _, o = obs("Hace tiempo que tuve una convulsión")
    assert o["seizure"].temporality == "historical"


def test_review_6_structured_absent_does_not_hide_text_present():
    interp, o = obs("Me falta muchísimo el aire",
                    reported_symptoms=[{"symptom": "shortness_of_breath", "status": "absent"}])
    assert (o["shortness_of_breath"].status, o["shortness_of_breath"].origin) == ("present", "text")
    assert evaluate_alarms(interp, [], "ana")
    _, o = obs("Ya se me pasó la presión en el pecho",
               reported_symptoms=[{"symptom": "chest_pain", "status": "unknown"}])
    assert o["chest_pain"].status == "present"
    # structured present still wins over text (modifiers and unknown -> present).
    _, o = obs("No sé si tengo fiebre", reported_symptoms=[{"symptom": "fever", "onset": "sudden"}])
    assert (o["fever"].status, o["fever"].origin, o["fever"].onset) == ("present", "structured", "sudden")


def test_review_7_headache_clarification_round_trip_by_text():
    msg = "Me duele la cabeza. Empezó poco a poco y es leve; no tengo problemas del habla ni de visión."
    _, o = obs(msg)
    assert (o["headache"].onset, o["headache"].severity) == ("gradual", "mild")
    route, d = run({"message": msg, "astronaut_id": "ana"})
    assert route in ("out_of_coverage", "assessment")
    assert d is None or d.protocol_id != "neurologic_red_flags"
    for text in ("Me duele la cabeza de a poco, es poco intenso", "Dolor de cabeza ligero que empezó lentamente"):
        _, o = obs(text)
        assert (o["headache"].onset, o["headache"].severity) == ("gradual", "mild"), text


def test_review_8_acute_retention_candidate_needs_sudden_onset():
    def cand(message):
        [hit] = evaluate_alarms(interpret(AssistantRequest(message=message)), [], None)
        return hit.candidates[0].status
    assert cand("De repente no puedo orinar") == "compatible"
    assert cand("No puedo orinar") == "insufficient_evidence"


def test_request_kinds_and_hints():
    interp, _ = obs("¿Qué causa el mareo espacial?")
    assert interp.request_kind == "educational"
    assert interp.topic_hint == "dizziness_or_space_motion_sickness"
    interp, _ = obs("No me siento bien")
    assert interp.request_kind == "unclear" and interp.medical_signal
    interp, _ = obs("El oxímetro marca 88")
    assert interp.mentions_readings == ("heart_rate", "spo2")
    interp, _ = obs("Hola, ¿qué tal el día?")
    assert not interp.medical_signal


# --- alarms ---


def test_negated_historical_hypothetical_never_trigger():
    for message in ["No me falta el aire", "Hace dos años tuve una convulsión",
                    "¿Qué pasa si alguien no responde?", "No tengo dolor de pecho ni palpitaciones"]:
        interp, _ = obs(message)
        assert not evaluate_alarms(interp, [], "ana"), message


def test_severe_breathlessness_ignores_readings():
    interp, _ = obs("Me falta mucho el aire")
    hits = evaluate_alarms(interp, [], "ana")
    assert [h.protocol_id for h in hits] == ["breathing_difficulty"]
    route, d = run({"message": "Me falta mucho el aire", "astronaut_id": "ana"},
                   readings=[{"kind": "spo2", "value": 97, "unit": "%", "recorded_at": "2026-11-14T11:59:00Z",
                              "quality": "good", "source": "manual"}])
    assert route == "alarm" and d.urgency == "immediate"


def test_simultaneous_alarms_keep_all_and_dedupe():
    interp, _ = obs("Mi compañero no responde y no respira bien. Además suena la alarma de humo.")
    hits = evaluate_alarms(interp, [], "ana")
    d = decide(hits, CATALOG, None)
    assert d.protocol_id == "loss_of_consciousness_or_seizure"
    assert d.additional_protocol_ids == ["breathing_difficulty", "cabin_environment_alert"]
    assert d.action.lower().count("emergency") >= 2  # one action per card, deduped
    assert d.notify == ["crew", "mission control (if the link is up)"]
    assert any("type smoke" in f.detail and "REPORTED" in f.detail for f in d.findings)
    assert d.summary.startswith(CATALOG["loss_of_consciousness_or_seizure"].actions["unresponsive"].text)
    assert d.clarifying_question is None


def test_events_provenance_and_targeting():
    co2 = OperationalEvent(id="e1", type="cabin_co2", origin="ship:eclss", occurred_at=T0,
                           status="active", provenance="confirmed", astronaut_ids=["luis"])
    interp, _ = obs("Estoy bien")
    assert not evaluate_alarms(interp, [co2], "ana")  # other crew member only
    assert evaluate_alarms(interp, [co2], "luis")[0].action_key == "confirmed_event"
    sim = co2.model_copy(update={"type": "radiation", "provenance": "simulated", "astronaut_ids": []})
    d = decide(evaluate_alarms(interp, [sim], "ana"), CATALOG, None)
    assert d.protocol_id == "radiation_alert" and "SIMULATED" in d.action
    assert any("SIMULATED" in f.detail and f.source == "event:e1" for f in d.findings)
    assert d.possible_causes == []


# --- case rules and decide ---


def test_isolated_rgb_reading_has_no_cause():
    route, d = run({"message": "La muestra de orina salió de color rojizo", "astronaut_id": "ana"},
                   readings=[{"kind": "urine_color", "value_text": "#B04030", "unit": "rgb_hex",
                              "recorded_at": "2026-11-14T11:00:00Z", "quality": "good", "source": "manual"}])
    assert route == "out_of_coverage" and d is None


def test_urine_reading_described_not_interpreted():
    route, d = run({"message": "Me arde al orinar", "astronaut_id": "ana"},
                   readings=[{"kind": "urine_ph", "value": 8.5, "unit": "pH",
                              "recorded_at": "2026-11-14T11:00:00Z", "quality": "good", "source": "manual"}])
    assert d.protocol_id == "urinary_symptoms"
    [reading] = [f for f in d.findings if f.kind == "reading"]
    assert "does not indicate blood" in reading.detail and reading.source == "sqlite:urine_ph"
    assert [c.id for c in d.possible_causes] == ["bladder_infection"]


def test_fever_flank_kidney_infection():
    _, d = run({"message": "Tengo fiebre y dolor en el costado", "astronaut_id": "ana"})
    assert d.urgency == "review_required"
    assert "urinary_symptoms.prompt_review" in [r.rule_id for r in d.matched_rules]
    causes = {c.id: c.status for c in d.possible_causes}
    assert causes["kidney_infection"] == "compatible"
    assert d.additional_protocol_ids == ["fever_or_respiratory_illness"]


def test_muscle_rhabdo_rule_out_and_sensor_never_triggers():
    _, d = run({"message": "Después del entrenamiento intenso tengo dolor muscular fuerte y la orina color cola",
                "astronaut_id": "ana"})
    assert {c.id: c.status for c in d.possible_causes}["rhabdomyolysis"] == "rule_out"
    route, d = run({"message": "Revisa el sensor muscular", "astronaut_id": "ana"},
                   readings=[{"kind": "muscle_density", "value": 0.2, "unit": "g/cm3",
                              "recorded_at": "2026-11-14T11:00:00Z", "quality": "good", "source": "manual"}])
    assert d is None


def test_dizziness_context():
    _, d = run({"message": "Estoy mareado", "astronaut_id": "ana"})
    assert {c.id: c.status for c in d.possible_causes} == {"space_motion_sickness": "insufficient_evidence"}
    _, d = run({"message": "Estoy mareado en los primeros días de adaptación", "astronaut_id": "ana"})
    assert {c.id: c.status for c in d.possible_causes} == {"space_motion_sickness": "compatible"}


def test_spo2_suspect_asks_one_question_and_reports_staleness():
    route, d = run({"message": "¿Está bien mi saturación?", "astronaut_id": "ana"},
                   readings=[{"kind": "spo2", "value": 88, "unit": "%", "recorded_at": "2026-11-14T11:59:00Z",
                              "quality": "suspect", "source": "serial:pulse"}])
    assert route == "clarify" and d.urgency == "undetermined"
    assert d.clarifying_question == CATALOG["breathing_difficulty"].questions["symptoms_and_repeat"]
    spo2 = next(f for f in d.findings if f.source == "sqlite:spo2")
    assert "88 %" in spo2.detail and "2026-11-14T11:59:00Z" in spo2.detail and "suspect" in spo2.detail
    assert "finding, not a cause" in spo2.detail
    assert any(f.kind == "data_gap" and f.source == "sqlite:heart_rate" for f in d.findings)
    assert d.possible_causes == []
    _, d = run({"message": "¿Está bien mi saturación?", "astronaut_id": "ana"},
               readings=[{"kind": "spo2", "value": 97, "unit": "%", "recorded_at": "2026-11-14T11:50:00Z",
                          "quality": "good", "source": "manual"}])
    assert "OLD" in next(f for f in d.findings if f.source == "sqlite:spo2").detail


def test_radiation_question_with_urine_only():
    route, d = run({"message": "¿Estuve expuesto a radiación? Solo tengo los datos de orina", "astronaut_id": "ana"},
                   readings=[{"kind": "urine_radiation_marker", "value": 0.4, "unit": "a.u.",
                              "recorded_at": "2026-11-14T11:00:00Z", "quality": "good", "source": "manual"}])
    assert route == "assessment" and d.urgency == "informational"
    assert d.possible_causes == []
    gaps = [f.detail for f in d.findings if f.kind == "data_gap"]
    assert any("dosimetry" in g for g in gaps)
    assert any("does not provide an exposure estimate" in f.detail for f in d.findings if f.kind == "reading")


def test_decide_sources_and_rules():
    _, d = run({"message": "Tengo fiebre y tos", "astronaut_id": "ana"})
    assert [s.id for s in d.protocol_sources] == [
        "fever_or_respiratory_illness@2.1.0#medlineplus_fever",
        "fever_or_respiratory_illness@2.1.0#cdc_respiratory_viruses",
        "fever_or_respiratory_illness@2.1.0#medlineplus_breathing_first_aid",
    ]
    assert all(s.kind == "protocol" for s in d.protocol_sources)
    assert d.matched_rules[0].protocol_version == "2.1.0"
    assert d.clarifying_question is None
    assert d.summary.index(d.action) == 0
    assert decide([], CATALOG, None).protocol_id is None


def test_unclear_asks_generic_question_and_uncovered_symptom_is_out_of_coverage():
    assert run({"message": "Me siento mal", "astronaut_id": "ana"}) == ("clarify", None)
    assert run({"message": "Me duele el oído", "astronaut_id": "ana"}) == ("out_of_coverage", None)
    assert GENERIC_CLARIFYING_QUESTION.endswith("?")


def test_fainting_recovery_question_for_third_party():
    route, d = run({"message": "Luis se desmayó", "astronaut_id": "ana"})
    assert route == "clarify"
    assert d.clarifying_question == CATALOG["loss_of_consciousness_or_seizure"].questions["recovered"]
    route, d = run({"message": "Me desmayé hace un rato pero ya estoy bien", "astronaut_id": "ana"})
    assert route == "assessment" and d.urgency == "review_required"


# --- acceptance table ---


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_case_table(case):
    route, d = run(case["request"], case["events"], case["readings"])
    assert route == case["expect_route"]
    if d is None:
        assert case["expect_protocol"] is None
        return
    assert d.protocol_id == case["expect_protocol"]
    assert d.urgency == case["expect_urgency"]
    if case["expect_not_protocol"]:
        assert case["expect_not_protocol"] not in [d.protocol_id, *d.additional_protocol_ids]
    assert "%" not in d.action
    for cause in d.possible_causes:
        assert cause.id in {c.id for c in CATALOG[d.protocol_id].candidates} | {
            c.id for p in d.additional_protocol_ids for c in CATALOG[p].candidates}


def test_case_table_covers_every_card():
    activating = {c["card"] for c in CASES if c["card"] and c["expect_protocol"] == c["card"]}
    near = {c["card"] for c in CASES if c["expect_not_protocol"]}
    assert activating == near == set(CATALOG)
