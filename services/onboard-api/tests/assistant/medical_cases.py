"""Synthetic acceptance cases for POST /assistant/messages (plan §7).

One activating case and one near case per card (the near case must not activate
that card, neither as primary nor as additional protocol), plus extra acceptance
scenarios. Clock T0 = 2026-11-14T12:00:00Z (tests/conftest.py).

Keys:
- request: POST body. events: OperationalEvent dicts to inject. readings: POST /readings bodies.
- expect_protocol: primary protocol_id (None: no card). expect_not_protocol: card that must be
  absent from protocol_id and additional_protocol_ids.
- expect_urgency: response urgency. Routes without a card follow the graph's fixed replies:
  out_of_coverage -> "review_required", educational -> "informational".
- expect_route: triage route, for in-process tests. Route "clarify" without a card
  (request_kind "unclear") asks triage.GENERIC_CLARIFYING_QUESTION; expect_urgency "undetermined".
"""

FRESH = "2026-11-14T11:59:00Z"  # 60 s before T0
STALE = "2026-11-14T11:50:00Z"  # 600 s before T0 (> 300 s policy for pulse and SpO2)
FUTURE = "2026-11-14T12:10:00Z"  # 600 s after T0: future-dated, flagged like stale


def _req(message: str, **extra: object) -> dict:
    return {"message": message, "astronaut_id": "ana", **extra}


def _reading(kind: str, value=None, unit: str = "", recorded_at: str = FRESH, quality: str = "good",
             value_text: str | None = None, source: str = "manual") -> dict:
    body = {"astronaut_id": "ana", "kind": kind, "unit": unit, "recorded_at": recorded_at,
            "quality": quality, "source": source}
    body["value" if value_text is None else "value_text"] = value if value_text is None else value_text
    return body


def _event(type_: str, provenance: str = "confirmed", status: str = "active", origin: str = "ship:eclss") -> dict:
    return {"id": f"evt-{type_}-{provenance}-{status}", "type": type_, "origin": origin,
            "occurred_at": "2026-11-14T11:58:00Z", "status": status, "provenance": provenance,
            "astronaut_ids": []}


def _case(name, card, message, expect_protocol, expect_urgency, expect_route, *, near=False,
          events=(), readings=(), **request_extra) -> dict:
    return {
        "name": name,
        "card": card,
        "request": _req(message, **request_extra),
        "events": list(events),
        "readings": list(readings),
        "expect_protocol": expect_protocol,
        "expect_not_protocol": card if near else None,
        "expect_urgency": expect_urgency,
        "expect_route": expect_route,
    }


BR = "breathing_difficulty"
CHEST = "chest_pain"
PAL = "palpitations"
NEURO = "neurologic_red_flags"
LOC = "loss_of_consciousness_or_seizure"
ALLERGY = "severe_allergic_reaction"
FEVER = "fever_or_respiratory_illness"
DIZ = "dizziness_or_space_motion_sickness"
VOM = "vomiting_diarrhea_or_dehydration"
ABD = "abdominal_pain_or_gi_bleeding"
HEAT = "heat_illness"
URI = "urinary_symptoms"
MUSCLE = "muscle_symptoms"
INJ = "injury_bleeding_or_burn"
CABIN = "cabin_environment_alert"
RAD = "radiation_alert"

CASES: list[dict] = [
    # 1 breathing
    _case("breathing_severe_spo2_97", BR, "Me falta mucho el aire de repente", BR, "immediate", "alarm",
          readings=[_reading("spo2", 97, "%")]),
    _case("breathing_negated", BR, "No me falta el aire, pero tengo tos y algo de fiebre", FEVER,
          "review_required", "assessment", near=True),
    # 2 chest pain
    _case("chest_pressure_cold_sweat", CHEST, "Siento presión en el pecho desde hace un rato y sudor frío",
          CHEST, "immediate", "alarm"),
    _case("chest_negated", CHEST, "No me duele el pecho; tengo palpitaciones desde esta mañana", PAL,
          "review_required", "assessment", near=True),
    # 3 palpitations
    _case("palpitations_recurrent", PAL, "Tengo palpitaciones desde hace varios días que van y vienen", PAL,
          "review_required", "assessment"),
    _case("palpitations_negated", PAL, "No tengo palpitaciones, solo tos desde ayer", FEVER,
          "review_required", "assessment", near=True),
    # 4 neurologic
    _case("neuro_resolved_weakness", NEURO,
          "De repente no podía hablar bien y tuve debilidad en el brazo derecho, ya se me pasó",
          NEURO, "immediate", "alarm"),
    _case("neuro_negated", NEURO, "No se me traba el habla ni tengo debilidad; tengo tos y fiebre", FEVER,
          "review_required", "assessment", near=True),
    _case("neuro_mild_headache", NEURO, "Tengo dolor de cabeza leve desde la mañana y fiebre", FEVER,
          "review_required", "assessment", near=True),
    # 5 loss of consciousness
    _case("loc_crewmate_unresponsive", LOC, "Mi compañero no responde", LOC, "immediate", "alarm"),
    _case("loc_negated", LOC, "No me desmayé; tengo tos desde ayer", FEVER, "review_required",
          "assessment", near=True),
    _case("loc_historical", LOC, "Hace dos años me desmayé, pero ahora tengo tos", FEVER,
          "review_required", "assessment", near=True),
    # 6 allergy
    _case("allergy_throat", ALLERGY, "Comí algo nuevo y se me está cerrando la garganta", ALLERGY,
          "immediate", "alarm"),
    _case("allergy_negated", ALLERGY,
          "No tengo ronchas ni hinchazón en la garganta; me duele el estómago desde ayer", ABD,
          "review_required", "assessment", near=True),
    # 7 fever
    _case("fever_cough", FEVER, "Tengo fiebre y tos desde ayer", FEVER, "review_required", "assessment"),
    _case("fever_negated", FEVER, "Sin fiebre ni tos; me arde al orinar", URI, "review_required",
          "assessment", near=True),
    # 8 dizziness
    _case("dizziness_adaptation", DIZ,
          "Estoy mareado desde que llegamos, en los primeros días de adaptación a la microgravedad", DIZ,
          "review_required", "assessment"),
    _case("dizziness_negated", DIZ, "No tengo mareo; tengo calambres después del ejercicio", MUSCLE,
          "review_required", "assessment", near=True),
    # 9 vomiting / dehydration
    _case("vomiting_cannot_keep_fluids", VOM, "Llevo todo el día vomitando y no puedo retener líquidos", VOM,
          "review_required", "assessment"),
    _case("vomiting_negated", VOM, "No he vomitado ni tengo diarrea; me duele el costado y tengo fiebre", URI,
          "review_required", "assessment", near=True),
    # 10 abdominal / GI bleeding
    _case("gi_blood_in_vomit", ABD, "Vomité sangre hace un momento", ABD, "immediate", "alarm"),
    _case("abdominal_negated", ABD, "No tengo dolor abdominal; tengo ardor al orinar", URI,
          "review_required", "assessment", near=True),
    # 11 heat
    _case("heat_confusion", HEAT, "Después de trabajar con mucho calor está confundido", HEAT, "immediate",
          "alarm"),
    _case("heat_negated", HEAT, "Tengo calambres en las piernas después del ejercicio, sin calor en la cabina",
          MUSCLE, "review_required", "assessment", near=True),
    # 12 urinary
    _case("urinary_fever_flank", URI, "Tengo fiebre y dolor en el costado", URI, "review_required", "assessment"),
    _case("urinary_negated", URI, "No me arde al orinar; tengo tos y fiebre", FEVER, "review_required",
          "assessment", near=True),
    _case("urinary_rgb_only", URI, "La muestra de orina salió de color rojizo pero no tengo síntomas", None,
          "review_required", "out_of_coverage", near=True,
          readings=[_reading("urine_color", unit="rgb_hex", value_text="#B04030")]),
    # 13 muscle
    _case("muscle_rhabdo", MUSCLE,
          "Después del entrenamiento intenso tengo dolor muscular fuerte y la orina color cola", MUSCLE,
          "review_required", "assessment"),
    _case("muscle_negated", MUSCLE, "No tengo dolor muscular; me falta el aire al hacer ejercicio", BR,
          "review_required", "assessment", near=True),
    # 14 injury
    _case("injury_heavy_bleeding", INJ, "Me corté la mano y sangra mucho, no para de sangrar", INJ,
          "immediate", "alarm"),
    _case("injury_negated", INJ, "No me golpeé ni tengo heridas; me arde al orinar", URI, "review_required",
          "assessment", near=True),
    # 15 cabin
    _case("cabin_co2_confirmed_normal_spo2", CABIN, "Me duele la cabeza", CABIN, "immediate", "alarm",
          events=[_event("cabin_co2")], readings=[_reading("spo2", 99, "%")]),
    _case("cabin_negated", CABIN, "No suena ninguna alarma de CO2; tengo tos", FEVER, "review_required",
          "assessment", near=True),
    _case("cabin_resolved_event", CABIN, "Tengo tos", FEVER, "review_required", "assessment", near=True,
          events=[_event("cabin_co2", status="resolved")]),
    # 16 radiation
    _case("radiation_confirmed", RAD, "Tengo náuseas", RAD, "immediate", "alarm",
          events=[_event("radiation", origin="dosimeter:area-2")]),
    _case("radiation_negated", RAD, "No suena ninguna alarma de radiación; tengo diarrea y retengo líquidos",
          VOM, "review_required", "assessment", near=True),
    # Extra acceptance scenarios
    _case("breathing_sudden_stale_spo2", BR, "Me falta el aire de repente", BR, "immediate", "alarm",
          readings=[_reading("spo2", 98, "%", recorded_at=STALE)]),
    _case("spo2_suspect_isolated", BR, "¿Está bien mi saturación?", BR, "undetermined", "clarify",
          readings=[_reading("spo2", 88, "%", quality="suspect")]),
    _case("dizziness_with_speech_change", NEURO, "Estoy mareado y se me traba el habla", NEURO, "immediate",
          "alarm"),
    _case("palpitations_with_chest_pain", PAL, "Tengo palpitaciones y dolor en el pecho", PAL, "immediate",
          "alarm"),
    _case("urinary_sudden_retention", URI, "No puedo orinar, empezó de repente", URI, "immediate", "alarm"),
    _case("radiation_simulated", RAD, "¿Qué hago?", RAD, "immediate", "alarm",
          events=[_event("radiation", provenance="simulated", origin="dosimeter:drill")]),
    _case("radiation_urine_only", RAD, "¿Estuve expuesto a radiación? Solo tengo los datos de orina", RAD,
          "informational", "assessment",
          readings=[_reading("urine_radiation_marker", 0.4, "a.u.")]),
    _case("cabin_reported_co2", CABIN, "Suena la alarma de CO2", CABIN, "immediate", "alarm"),
    _case("cabin_multiple_crew", CABIN, "Varios tripulantes tenemos dolor de cabeza y náuseas", CABIN,
          "immediate", "alarm"),
    _case("simultaneous_unresponsive_breathing", LOC, "Mi compañero no responde y no respira bien", LOC,
          "immediate", "alarm"),
    _case("unclear_unwell", None, "No me siento bien", None, "undetermined", "clarify"),
    _case("out_of_coverage_ear", None, "Me duele el oído", None, "review_required", "out_of_coverage"),
    _case("hypothetical_chest_pain", CHEST, "¿Qué pasa si alguien tiene dolor de pecho?", None,
          "informational", "educational", near=True),
]
