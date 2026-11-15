"""Deterministic triage rules (plan §4). Pure functions, no I/O.

evaluate_alarms -> immediate hits only (cards, request and events; never readings).
evaluate_case   -> review_required / undetermined / informational hits, incl. readings.
Negated, historical and hypothetical observations never trigger a rule. Resolved
acute signs trigger only where the card says so (neurologic signs, seizure,
blood in vomit, severe/sudden breathlessness, chest pain pattern, fainting review). Readings never cancel a symptom or event alarm.
"""

from collections.abc import Iterable
from datetime import UTC

from onboard_api.assistant.workflows.medical.state import (
    CandidateHit,
    Decision,
    Interpretation,
    Observation,
    Protocol,
    ReadingsContext,
    Route,
    RuleHit,
    VitalReading,
)
from onboard_api.schemas.assistant import (
    ActionStep,
    EvidenceFlag,
    Finding,
    GuideSource,
    MatchedRule,
    MissionProcedure,
    OperationalEvent,
    PossibleCause,
    Urgency,
)
from onboard_api.schemas.readings import is_simulated_source

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

# Asked when a report names no concrete symptom ("I feel bad", "malestar físico").
GENERIC_CLARIFYING_QUESTION = "What do you feel right now: pain, shortness of breath, dizziness, nausea or something else?"

URGENCY_RANK: dict[str, int] = {"immediate": 0, "review_required": 1, "undetermined": 2, "informational": 3}

LABELS = {
    "shortness_of_breath": "Shortness of breath", "abnormal_breathing": "Abnormal breathing",
    "chest_pain": "Chest pain or pressure", "cold_sweat": "Cold sweat", "palpitations": "Palpitations",
    "speech_change": "Speech change", "facial_droop": "Facial droop", "one_sided_weakness": "Weakness on one side",
    "vision_loss": "Vision loss", "sudden_severe_headache": "Sudden severe headache", "headache": "Headache",
    "unresponsive": "Unresponsive", "fainting": "Fainting or loss of consciousness", "seizure": "Seizure",
    "throat_swelling": "Throat or tongue swelling", "hives": "Hives", "allergen_exposure": "Possible allergen exposure",
    "fever": "Fever", "chills": "Chills", "cough": "Cough", "malaise": "General malaise", "confusion": "Confusion",
    "stiff_neck": "Stiff neck", "dizziness": "Dizziness", "nausea": "Nausea", "vomiting": "Vomiting",
    "diarrhea": "Diarrhea", "low_fluid_intake": "Low fluid intake", "unable_to_keep_fluids": "Cannot keep fluids down",
    "low_urine_output": "Low urine output", "vomiting_blood": "Vomiting blood", "abdominal_pain": "Abdominal pain",
    "black_stool": "Black stool", "blood_in_stool": "Blood in stool", "heat_exposure": "Heat exposure",
    "heavy_sweating": "Heavy sweating", "collapse": "Collapse", "urinary_burning": "Burning when urinating",
    "urinary_urgency": "Urinary urgency", "flank_pain": "Flank pain", "visible_blood_in_urine": "Visible blood in urine",
    "unable_to_urinate": "Unable to urinate", "muscle_pain": "Muscle pain", "muscle_cramps": "Cramps",
    "muscle_weakness": "Muscle weakness", "dark_urine": "Tea- or cola-colored urine reported",
    "intense_exertion": "Physical exertion", "injury": "Blow or injury", "head_injury": "Head injury",
    "bleeding": "Bleeding", "heavy_bleeding": "Heavy bleeding that continues", "burn": "Burn",
    "severe_burn": "Severe burn", "repeated_vomiting": "Repeated vomiting", "multiple_crew_symptoms": "Several crew members with symptoms at once",
    "cabin_alarm_reported": "Cabin alarm", "radiation_alert_reported": "Radiation alert",
}
_EVENT_LABELS = {
    "cabin_pressure": "cabin pressure", "cabin_smoke": "smoke", "cabin_co2": "CO₂",
    "cabin_air_other": "other air alarm", "radiation": "radiation",
}
_ALARM_TYPES = {"co2": "CO₂", "smoke": "smoke", "pressure": "pressure", "other": "other"}
_KIND_LABELS = {
    "heart_rate": "Pulse", "spo2": "SpO₂", "muscle_density": "Muscle sensor", "urine_ph": "Urine pH",
    "urine_salinity": "Urine salinity/conductivity", "urine_color": "Urine color (RGB)",
    "urine_temperature": "Urine sample temperature", "urine_radiation_marker": "Urinary radiation marker",
}
# Visual reference ranges, mirroring the seeded sensor_config. Not diagnostic.
REFERENCE = {"spo2": (95.0, 100.0), "heart_rate": (60.0, 100.0)}
_VITALS = ("spo2", "heart_rate")
_URINE = ("urine_ph", "urine_salinity", "urine_color", "urine_temperature")
PERTINENT_READINGS = {
    BR: _VITALS, CHEST: _VITALS, PAL: ("heart_rate", "spo2"), LOC: _VITALS, ALLERGY: _VITALS,
    CABIN: _VITALS, HEAT: _VITALS, FEVER: _VITALS, DIZ: _VITALS, NEURO: (),
    VOM: ("heart_rate", "urine_color"), URI: _URINE, MUSCLE: ("muscle_density", "urine_color"),
    RAD: ("urine_radiation_marker",), INJ: ("heart_rate",), ABD: ("heart_rate",),
}
_READING_NOTES = {
    **{k: "sample property: does not indicate blood, body temperature, infection, hydration or radiation" for k in _URINE},
    "muscle_density": "method and unit pending: does not trigger clinical hypotheses",
    "urine_radiation_marker": "the urine module does not provide an exposure estimate",
}


# --- helpers ---


def _get(interp: Interpretation, code: str, resolved: bool = False) -> Observation | None:
    """Present observation that may trigger a rule (never negated/historical/hypothetical)."""
    ok = ("current", "resolved") if resolved else ("current",)
    for o in interp.observations:
        if o.symptom == code and o.status == "present" and o.temporality in ok:
            return o
    return None


def _any(interp: Interpretation, *codes: str, resolved: bool = False) -> list[Observation]:
    return [o for c in codes if (o := _get(interp, c, resolved))]


def _absent(interp: Interpretation, code: str) -> bool:
    return any(o.symptom == code and o.status == "absent" for o in interp.observations)


def _iso(value) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def symptom_finding(o: Observation) -> Finding:
    parts = [LABELS[o.symptom]]
    reported_alert = o.symptom in ("cabin_alarm_reported", "radiation_alert_reported")
    if o.symptom == "cabin_alarm_reported":
        parts.append(f"type {_ALARM_TYPES.get(o.context or 'other', 'other')}")
    if reported_alert:
        parts.append("REPORTED in text, not confirmed by the ship")
    if o.temporality == "resolved":
        parts.append("already eased")
    if o.onset == "sudden":
        parts.append("sudden onset")
    if o.severity == "severe":
        parts.append("high intensity")
    if o.persistence in ("ongoing", "recurrent"):
        parts.append({"ongoing": "persistent", "recurrent": "recurrent"}[o.persistence])
    if o.subject == "other":
        parts.append("reported by another person")
    detail = "; ".join(parts) + (f' ("{o.evidence}")' if o.origin == "text" else "")
    return Finding(
        kind="event" if reported_alert else "symptom",
        detail=detail,
        source="report" if o.origin == "text" else "structured",
    )


def event_finding(e: OperationalEvent) -> Finding:
    provenance = "CONFIRMED by the ship" if e.provenance == "confirmed" else "SIMULATED (labelled drill)"
    state = "active" if e.status == "active" else "resolved"
    return Finding(
        kind="event",
        detail=f"{_EVENT_LABELS[e.type].capitalize()} event {state}, {provenance}; origin {e.origin}; {_iso(e.occurred_at)}",
        source=f"event:{e.id}",
    )


def _hit(
    pid: str,
    rule: str,
    urgency: Urgency,
    action: str,
    obs: Iterable[Observation | None] = (),
    extra: Iterable[Finding] = (),
    candidates: Iterable[CandidateHit] = (),
    question: str | None = None,
) -> RuleHit:
    return RuleHit(
        rule_id=f"{pid}.{rule}",
        protocol_id=pid,
        urgency=urgency,
        action_key=action,
        findings=tuple(symptom_finding(o) for o in obs if o) + tuple(extra),
        candidates=tuple(candidates),
        question_key=question,
    )


def _cand(cid: str, status, obs: Iterable[Observation | None] = (), missing: Iterable[str] = ()) -> CandidateHit:
    evidence = tuple(dict.fromkeys(LABELS[o.symptom] for o in obs if o))
    return CandidateHit(cid, status, evidence, tuple(missing))


def _relevant_events(events: list[OperationalEvent], astronaut_id: str | None) -> list[OperationalEvent]:
    return [
        e for e in events
        if e.status == "active" and (not e.astronaut_ids or astronaut_id in e.astronaut_ids)
    ]


def _reports_symptoms(interp: Interpretation) -> bool:
    return any(o.status == "present" and o.temporality in ("current", "resolved") for o in interp.observations)


# --- alarms ---


def evaluate_alarms(
    interp: Interpretation, events: list[OperationalEvent], astronaut_id: str | None
) -> list[RuleHit]:
    g = lambda code, resolved=False: _get(interp, code, resolved)  # noqa: E731
    hits: list[RuleHit] = []

    def add(pid: str, rule: str, action: str, obs=(), **kw) -> None:
        hits.append(_hit(pid, rule, "immediate", action, obs, **kw))

    # 1. Loss of consciousness / seizure (priority 10).
    if o := g("unresponsive"):
        add(LOC, "unresponsive", "unresponsive", [o])
    if o := g("seizure", True):
        # ponytail: any observed seizure counts as "first" (crew history is unknown here).
        add(LOC, "seizure", "seizure", [o])

    # 2. Breathing: abnormal breathing, or intense/sudden breathlessness, whatever the SpO2.
    if o := g("abnormal_breathing"):
        add(BR, "abnormal_breathing", "immediate", [o])
    sob = g("shortness_of_breath")
    # The card alarms on intensity/suddenness, so an episode that already eased still counts.
    sob_any = g("shortness_of_breath", True)
    severe_sob = sob_any if sob_any and (sob_any.severity == "severe" or sob_any.onset == "sudden") else None
    if severe_sob:
        add(BR, "severe_or_sudden", "immediate", [severe_sob])

    # 3-4. Ship events (confirmed or labelled simulated), then text-reported alerts.
    for e in _relevant_events(events, astronaut_id):
        confirmed = e.provenance == "confirmed"
        if e.type == "radiation":
            cands = [_cand("possible_exposure", "rule_out", missing=["dose measured by dosimetry"])] if confirmed else []
            add(RAD, f"event_{e.provenance}", "confirmed_event" if confirmed else "simulated_event",
                extra=[event_finding(e)], candidates=cands)
        else:
            cands = [_cand("environmental_exposure", "rule_out", missing=["cabin environmental measurement"])] if confirmed else []
            add(CABIN, f"event_{e.provenance}", "confirmed_event" if confirmed else "simulated_event",
                extra=[event_finding(e)], candidates=cands)
    if o := g("cabin_alarm_reported"):
        add(CABIN, "reported_alarm", "reported_alarm", [o], candidates=[
            _cand("environmental_exposure", "insufficient_evidence", [o], ["event confirmation by the ship"])])
    if o := g("multiple_crew_symptoms"):
        add(CABIN, "multiple_crew", "multiple_crew", [o], candidates=[
            _cand("environmental_exposure", "insufficient_evidence", [o], ["cabin environmental measurement"])])
    if o := g("radiation_alert_reported"):
        add(RAD, "reported_alert", "reported_alert", [o])

    # 5. Severe allergic reaction.
    throat = g("throat_swelling")
    trigger = _any(interp, "hives", "allergen_exposure")
    breathing = [x for x in (sob, g("abnormal_breathing")) if x]
    if throat or (trigger and breathing):
        status = "compatible" if trigger else "rule_out"
        obs = [throat, *trigger, *breathing]
        add(ALLERGY, "airway", "immediate", obs, candidates=[_cand("anaphylaxis", status, obs)])

    # 6. Neurologic focal signs, current or already resolved.
    focal = _any(interp, "speech_change", "facial_droop", "one_sided_weakness", "vision_loss",
                 "sudden_severe_headache", resolved=True)
    if focal:
        add(NEURO, "focal_signs", "immediate", focal, candidates=[_cand("stroke_tia", "rule_out", focal)])
        if dz := g("dizziness", True):
            add(DIZ, "with_neurologic_signs", "with_neurologic_signs", [dz])

    # 7. Chest pain with a concerning pattern, current or already eased (card: pressure that "reaparece").
    cp = g("chest_pain", True)
    if cp:
        companions = _any(interp, "shortness_of_breath", "cold_sweat", "dizziness")
        if (cp.context == "pressure" or cp.severity == "severe" or cp.onset == "sudden"
                or cp.persistence in ("ongoing", "recurrent") or companions):
            add(CHEST, "concerning_pattern", "immediate", [cp, *companions],
                candidates=[_cand("acs", "rule_out", [cp, *companions])])

    # 8. Injury, bleeding, burn.
    if o := g("heavy_bleeding"):
        add(INJ, "heavy_bleeding", "heavy_bleeding", [o])
    burn = g("severe_burn") or ((b := g("burn")) and b.severity == "severe" and b)
    if burn:
        add(INJ, "severe_burn", "severe_burn", [burn])
    head = g("head_injury", True)
    head_flags = _any(interp, "repeated_vomiting", "confusion", "unresponsive", "seizure", "fainting", resolved=True)
    if head and head_flags:
        add(INJ, "head_injury_red_flags", "head_injury_red_flags", [head, *head_flags],
            candidates=[_cand("concussion", "rule_out", [head, *head_flags])])

    # 9. Abdominal pain / GI bleeding.
    if o := g("vomiting_blood", True):
        add(ABD, "blood_in_vomit", "immediate", [o])
    if o := g("black_stool", True):
        add(ABD, "black_stool", "immediate", [o])
    ab = g("abdominal_pain")
    if ab and ab.onset == "sudden" and ab.severity == "severe":
        add(ABD, "sudden_severe_pain", "immediate", [ab])

    # 10. Heat illness: confusion or collapse with heat exposure.
    heat = g("heat_exposure", True)
    heat_flags = _any(interp, "confusion", "collapse", "unresponsive", "fainting")
    if heat and heat_flags:
        add(HEAT, "confusion_or_collapse", "immediate", [heat, *heat_flags],
            candidates=[_cand("heat_stroke", "rule_out", [heat, *heat_flags])])

    # 11. Urinary: sudden inability to urinate (unknown onset is treated as sudden).
    utu = g("unable_to_urinate")
    if utu and utu.onset != "gradual":
        cand = (_cand("acute_retention", "compatible", [utu]) if utu.onset == "sudden" else
                _cand("acute_retention", "insufficient_evidence", [utu], ["sudden onset"]))
        add(URI, "acute_retention", "immediate", [utu], candidates=[cand])

    # 13. Fever with red flags.
    fever = g("fever")
    fever_flags = _any(interp, "confusion", "stiff_neck", "abnormal_breathing") + ([severe_sob] if severe_sob else [])
    if fever and fever_flags:
        add(FEVER, "red_flags", "immediate", [fever, *fever_flags])

    # 14. Vomiting / diarrhea with red flags.
    gi = _any(interp, "vomiting", "diarrhea", "nausea", "repeated_vomiting")
    gi_flags = _any(interp, "confusion", "fainting", "unresponsive")
    if gi and gi_flags:
        add(VOM, "red_flags", "immediate", [*gi, *gi_flags])
    if o := g("vomiting_blood", True):
        add(VOM, "blood_in_vomit", "immediate", [o])

    # 15. Palpitations with chest pain, major breathlessness or loss of consciousness.
    pal = g("palpitations", True)
    pal_flags = _any(interp, "chest_pain", "unresponsive") + _any(interp, "fainting", resolved=True)
    if severe_sob:
        pal_flags.append(severe_sob)
    if pal and pal_flags:
        add(PAL, "red_flags", "immediate", [pal, *pal_flags],
            candidates=[_cand("arrhythmia", "rule_out", [pal, *pal_flags])])

    return hits


# --- non-alarm case ---


def _out_of_range(r: VitalReading) -> bool:
    lo_hi = REFERENCE.get(r.kind)
    return bool(lo_hi and r.value is not None and not lo_hi[0] <= r.value <= lo_hi[1])


def evaluate_case(
    interp: Interpretation, events: list[OperationalEvent], readings: ReadingsContext
) -> list[RuleHit]:
    g = lambda code, resolved=False: _get(interp, code, resolved)  # noqa: E731
    hits: list[RuleHit] = []

    def add(pid, rule, urgency, action, obs=(), **kw) -> None:
        hits.append(_hit(pid, rule, urgency, action, obs, **kw))

    # Breathing without red flags.
    if sob := g("shortness_of_breath", True):
        resp = _any(interp, "cough", "fever")
        cands = [_cand("respiratory_cause", "compatible", [sob, *resp])] if resp else []
        add(BR, "new_no_red_flags", "review_required", "new_no_red_flags", [sob], candidates=cands)

    # Chest pain without the concerning pattern (or already resolved).
    if cp := g("chest_pain", True):
        add(CHEST, "new_pain", "review_required", "new_pain", [cp], candidates=[
            _cand("acs", "insufficient_evidence", [cp],
                  ["duration, character of the pain and accompanying symptoms"])])

    # Palpitations.
    if pal := g("palpitations", True):
        exertion = g("intense_exertion")
        hr = readings.latest.get("heart_rate")
        cands = []
        if exertion:
            cands.append(_cand("exertional_response", "compatible", [pal, exertion]))
        if hr and hr.quality != "good":
            cands.append(CandidateHit("artifact", "compatible", (f"Pulse with quality {hr.quality}",)))
        if not exertion or pal.persistence in ("ongoing", "recurrent") or g("dizziness", True):
            cands.append(_cand("arrhythmia", "rule_out", [pal, g("dizziness", True)], ["ECG"]))
        add(PAL, "review", "review_required", "review", [pal], candidates=cands)

    # Isolated SpO2 / pulse readings.
    for kind, pid in (("spo2", BR), ("heart_rate", PAL)):
        if interp.request_kind == "educational" or any(h.protocol_id == pid for h in hits):
            continue
        r = readings.latest.get(kind)
        abnormal = r is not None and _out_of_range(r)
        if not (kind in interp.mentions_readings or (abnormal and not _reports_symptoms(interp))):
            continue
        if r is None or r.stale or r.quality != "good" or abnormal:
            cands = []
            if kind == "heart_rate" and r is not None and r.quality != "good":
                cands = [CandidateHit("artifact", "compatible", (f"Pulse with quality {r.quality}",))]
            add(pid, f"reading_{kind}", "undetermined", "reading_check", candidates=cands,
                question="symptoms_and_repeat")
        else:
            add(pid, f"reading_{kind}", "informational", "reading_reference")

    # Headache without known onset/intensity: ask about red flags.
    if (h := g("headache")) and not g("sudden_severe_headache"):
        if h.severity not in ("mild", "moderate") and h.onset != "gradual":
            add(NEURO, "headache_check", "undetermined", "headache_check", [h], question="headache_red_flags")

    # Fainting: self-report or resolved -> review; another person, recovery unknown -> ask.
    if f := g("fainting", True):
        if f.subject == "self" or f.temporality == "resolved":
            add(LOC, "fainted_recovered", "review_required", "fainted_recovered", [f])
        else:
            add(LOC, "recovery_check", "undetermined", "recovery_check", [f], question="recovered")

    # Limited allergic symptoms.
    allergic = _any(interp, "hives", "allergen_exposure")
    if allergic:
        add(ALLERGY, "limited", "review_required", "limited", allergic, candidates=[
            _cand("anaphylaxis", "insufficient_evidence", allergic, ["breathing or throat involvement"])])

    # Fever / respiratory illness.
    resp = _any(interp, "fever", "chills", "cough", "malaise")
    if resp:
        febrile = _any(interp, "fever", "chills")
        cough = g("cough")
        status = "compatible" if febrile and cough else "insufficient_evidence"
        add(FEVER, "review", "review_required", "review", resp, candidates=[
            _cand("respiratory_infection", status, resp,
                  [] if status == "compatible" else ["measured fever and cough"])])

    # Dizziness without neurologic signs.
    if dz := g("dizziness", True):
        adaptation = any(o.context == "adaptation" for o in interp.observations if o.status == "present")
        losses = _any(interp, "vomiting", "diarrhea", "heavy_sweating", "low_fluid_intake",
                      "unable_to_keep_fluids", "low_urine_output")
        cands = [
            _cand("space_motion_sickness", "compatible", [dz]) if adaptation else
            _cand("space_motion_sickness", "insufficient_evidence", [dz],
                  ["mission phase and link to head movements"]),
        ]
        if losses:
            cands.append(_cand("dehydration", "compatible", [dz, *losses]))
        add(DIZ, "assessment", "review_required", "assessment", [dz], candidates=cands)

    # Vomiting / diarrhea / dehydration.
    gi = _any(interp, "vomiting", "diarrhea", "nausea", "repeated_vomiting")
    fluids = _any(interp, "unable_to_keep_fluids", "low_urine_output", "low_fluid_intake")
    if gi or fluids:
        losses = _any(interp, "vomiting", "diarrhea", "repeated_vomiting", "heavy_sweating")
        cands = []
        if losses or fluids:
            cands.append(_cand("dehydration", "compatible", [*losses, *fluids]))
        if gi:
            cands.append(_cand("gastrointestinal_illness", "compatible", gi))
        urgent = _any(interp, "unable_to_keep_fluids", "low_urine_output", "repeated_vomiting")
        persistent = any(o.persistence in ("ongoing", "recurrent") for o in gi)
        fluids_known = urgent or _absent(interp, "unable_to_keep_fluids") or _absent(interp, "low_urine_output")
        losing = _any(interp, "vomiting", "diarrhea")
        if urgent or persistent:
            add(VOM, "prompt_review", "review_required", "prompt_review", [*gi, *fluids], candidates=cands)
        elif losing and not fluids_known:
            add(VOM, "fluids_check", "undetermined", "fluids_check", [*gi, *fluids], candidates=cands,
                question="fluids_urine")
        else:
            add(VOM, "review", "review_required", "review", [*gi, *fluids], candidates=cands)

    # Abdominal pain / blood in stool.
    ab = g("abdominal_pain")
    blood = g("blood_in_stool", True)
    if ab or blood:
        prompt = blood or (ab and (ab.severity == "severe" or ab.persistence in ("ongoing", "recurrent")))
        companions = _any(interp, "vomiting", "diarrhea", "nausea")
        cands = [_cand("digestive_cause", "compatible", [ab, *companions])] if ab and companions else []
        action = "prompt_review" if prompt else "review"
        add(ABD, action, "review_required", action, [ab, blood], candidates=cands)

    # Heat illness with the person conscious.
    if heat := g("heat_exposure", True):
        exhaustion = _any(interp, "heavy_sweating", "dizziness", "nausea", "headache", "malaise")
        cramps = g("muscle_cramps")
        if exhaustion or cramps:
            cands = []
            if exhaustion:
                cands.append(_cand("heat_exhaustion", "compatible", [heat, *exhaustion]))
            if cramps:
                cands.append(_cand("heat_cramps", "compatible", [heat, cramps]))
            add(HEAT, "review", "review_required", "review", [heat, *exhaustion, cramps], candidates=cands)

    # Urinary symptoms.
    bladder = _any(interp, "urinary_burning", "urinary_urgency")
    flank = g("flank_pain")
    febrile = _any(interp, "fever", "chills")
    visible = g("visible_blood_in_urine")
    utu = g("unable_to_urinate")
    if bladder or flank or visible or utu:
        cands = []
        if bladder:
            cands.append(_cand("bladder_infection", "compatible", bladder))
        if flank and febrile:
            cands.append(_cand("kidney_infection", "compatible", [*febrile, flank]))
        stone_signs = [x for x in (flank if flank and (flank.severity == "severe" or flank.persistence == "recurrent") else None, visible) if x]
        if stone_signs:
            cands.append(_cand("kidney_stone", "compatible", stone_signs))
        elif flank and not febrile:
            cands.append(_cand("kidney_stone", "insufficient_evidence", [flank], ["intensity, waves of pain or visible blood"]))
        if utu:
            cands.append(_cand("acute_retention", "insufficient_evidence", [utu], ["sudden onset"]))
        prompt = (flank and febrile) or stone_signs
        action = "prompt_review" if prompt else "review"
        add(URI, action, "review_required", action, [*bladder, flank, *febrile, visible, utu], candidates=cands)

    # Muscle symptoms. Readings (muscle sensor, urine RGB) never trigger these.
    muscle = _any(interp, "muscle_pain", "muscle_cramps", "muscle_weakness")
    dark = g("dark_urine")
    context = _any(interp, "intense_exertion", "heat_exposure", resolved=True)
    if muscle or dark:
        strong = [o for o in muscle if o.symptom == "muscle_weakness" or o.severity == "severe"]
        if context and (strong or dark):
            add(MUSCLE, "suspected_rhabdo", "review_required", "suspected_rhabdo", [*muscle, dark, *context],
                candidates=[_cand("rhabdomyolysis", "rule_out", [*strong, dark, *context])])
        else:
            cands = []
            if muscle:
                cands.append(_cand("overexertion", "compatible", [*muscle, *context]) if context else
                             _cand("overexertion", "insufficient_evidence", muscle, ["prior exertion"]))
            if dark:
                cands.append(_cand("rhabdomyolysis", "insufficient_evidence", [dark, *muscle], ["prior exertion or heat"]))
            add(MUSCLE, "review", "review_required", "review", [*muscle, dark, *context], candidates=cands)

    # Injury, bleeding or burn without red flags.
    injury = _any(interp, "injury", "head_injury", "bleeding", "burn", resolved=True)
    if injury:
        cands = []
        if head := g("head_injury", True):
            symptoms = _any(interp, "headache", "dizziness", "nausea", "vomiting", "confusion")
            cands.append(_cand("concussion", "compatible", [head, *symptoms]) if symptoms else
                         _cand("concussion", "insufficient_evidence", [head], ["headache, dizziness, nausea or confusion"]))
        if g("injury", True) or head:
            cands.append(_cand("contusion", "insufficient_evidence", [g("injury", True) or head],
                               ["localized pain, swelling or bruising"]))
        add(INJ, "review", "review_required", "review", injury, candidates=cands)

    # Radiation question with no event and no dosimetry: state what is missing.
    if (interp.topic_hint == RAD and interp.request_kind != "educational"
            and not _absent(interp, "radiation_alert_reported")
            and not any(e.type == "radiation" and e.status == "active" for e in events)):
        add(RAD, "no_evidence", "informational", "no_evidence", extra=[
            Finding(kind="data_gap", source="events",
                    detail="No dosimeter event or ship radiation alert is available."),
            Finding(kind="data_gap", source="events",
                    detail="Without dosimetry an exposure cannot be estimated; the urine module does not estimate it."),
        ])

    return hits


# --- routing and aggregation ---


def select_route(interp: Interpretation, alarm_hits: list[RuleHit], case_hits: list[RuleHit]) -> Route:
    if alarm_hits:
        return "alarm"
    if case_hits:
        best = min(URGENCY_RANK[h.urgency] for h in case_hits)
        if best == URGENCY_RANK["undetermined"] and any(
            h.urgency == "undetermined" and h.question_key for h in case_hits
        ):
            return "clarify"
        return "assessment"
    if interp.request_kind == "unclear":
        return "clarify"  # no decision: the reply asks GENERIC_CLARIFYING_QUESTION
    if interp.request_kind == "educational":
        return "educational"
    # Out of coverage only for a concrete symptom or event the catalog does not cover.
    if interp.uncovered or _reports_symptoms(interp):
        return "out_of_coverage"
    return "clarify"  # a report with no concrete symptom yet: ask what the person feels


def _reading_detail(r: VitalReading, pids: list[str]) -> str:
    value = f"{r.value:g}" if r.value is not None else (r.value_text or "")
    parts = [
        f"{_KIND_LABELS.get(r.kind, r.kind)}: {value} {r.unit}",
        _iso(r.recorded_at),
        f"quality {r.quality}",
        f"source {r.source}",
        f"{r.age_seconds} s ago",
    ]
    if is_simulated_source(r.source):
        parts.append("SIMULATED: not a real measurement")
    if r.stale:
        parts.append("OLD, no longer current: confirms or excludes nothing")
    elif _out_of_range(r):
        lo, hi = REFERENCE[r.kind]
        parts.append(f"outside the visual reference {lo:g}–{hi:g} {r.unit} (finding, not a cause)")
    if r.quality != "good":
        parts.append("poor signal: repeat the measurement")
    if r.kind in _READING_NOTES:
        parts.append(_READING_NOTES[r.kind])
    if r.kind == "spo2" and CABIN in pids:
        parts.append("a normal SpO₂ does not rule out the cabin alert; conventional oximetry does not detect CO")
    return "; ".join(parts)


def _reading_findings(pids: list[str], readings: ReadingsContext) -> list[Finding]:
    kinds = list(dict.fromkeys(k for p in pids for k in PERTINENT_READINGS.get(p, ())))
    if not kinds:
        return []
    if not readings.available:
        return [Finding(kind="data_gap", detail="Readings unavailable: the repository could not be queried.",
                        source="sqlite", evidence_flags=["missing"])]
    out = []
    for kind in kinds:
        r = readings.latest.get(kind)
        if r is not None:
            out.append(Finding(kind="reading", detail=_reading_detail(r, pids), source=f"sqlite:{kind}",
                               evidence_flags=_reading_flags(r)))
        elif kind in REFERENCE:
            out.append(Finding(kind="data_gap", detail=f"No {_KIND_LABELS[kind]} reading.", source=f"sqlite:{kind}",
                               evidence_flags=["missing"]))
    return out


def _reading_flags(r: VitalReading) -> list[EvidenceFlag]:
    """Labels for the console (contract section 4). `stale` already covers future-dated readings."""
    flags: list[EvidenceFlag] = []
    if is_simulated_source(r.source):
        flags.append("simulated")
    if r.stale:
        flags.append("stale")
    if r.quality != "good":
        flags.append("poor_quality")
    return flags


def decide(hits: list[RuleHit], catalog: dict[str, Protocol], readings: ReadingsContext | None) -> Decision:
    if not hits:
        return Decision("informational", None, [], None, [], [], [], [], None, [], "")

    order = sorted(hits, key=lambda h: (URGENCY_RANK[h.urgency], catalog[h.protocol_id].priority))
    urgency = order[0].urgency
    lead = [h for h in order if h.urgency == urgency]
    primary = lead[0].protocol_id
    pids = list(dict.fromkeys(h.protocol_id for h in sorted(hits, key=lambda h: catalog[h.protocol_id].priority)))
    additional = [p for p in pids if p != primary]

    actions: list[str] = []
    notify: list[str] = []
    steps: list[ActionStep] = []
    procedures: list[MissionProcedure] = []
    missing: list[str] = []
    for h in lead:
        card = catalog[h.protocol_id]
        act = card.actions[h.action_key]
        if act.text not in actions:
            actions.append(act.text)
        notify += [n for n in act.notify if n not in notify]
        for st in act.steps:
            if all(st.text != x.text for x in steps):
                steps.append(ActionStep(text=st.text, who=st.who, source_ids=[
                    f"{h.protocol_id}@{card.version}#{sid}" for sid in st.source_ids]))
        # ponytail: no mission procedure is loaded yet, so every one is loaded=False;
        # look them up in a procedures store once the mission provides one.
        if act.mission_procedure and all(p.title != act.mission_procedure for p in procedures):
            procedures.append(MissionProcedure(title=act.mission_procedure))
        missing += [m for m in act.missing_guidance if m not in missing]

    matched: dict[str, MatchedRule] = {}
    findings: list[Finding] = []
    for h in order:
        matched.setdefault(h.rule_id, MatchedRule(
            rule_id=h.rule_id, protocol_id=h.protocol_id,
            protocol_version=catalog[h.protocol_id].version, urgency=h.urgency))
        findings += [f for f in h.findings if f not in findings]
    if readings is not None:
        findings += _reading_findings([primary, *additional], readings)

    causes: dict[str, PossibleCause] = {}
    for h in order:
        known = {c.id: c for c in catalog[h.protocol_id].candidates}
        for c in h.candidates:
            if c.candidate_id in known and c.candidate_id not in causes:
                card_c = known[c.candidate_id]
                causes[c.candidate_id] = PossibleCause(
                    id=c.candidate_id, label=card_c.label, status=c.status,
                    evidence_for=list(c.evidence_for), missing_data=list(c.missing_data),
                    source_ids=list(card_c.source_ids),
                )

    question = question_id = None
    if urgency == "undetermined":
        asked = next((h for h in lead if h.question_key in catalog[h.protocol_id].questions), None)
        if asked:
            question = catalog[asked.protocol_id].questions[asked.question_key]
            question_id = f"{asked.protocol_id}.{asked.question_key}"

    sources = [
        GuideSource(id=f"{pid}@{catalog[pid].version}#{s.id}", title=s.title, section=s.section,
                    url=s.url, kind="protocol")
        for pid in [primary, *additional]
        for s in catalog[pid].sources
    ]

    summary = "\n".join(actions) + "\n\n" + catalog[primary].summary
    if additional:
        summary += "\n\nAdditional signs: " + ", ".join(catalog[p].title for p in additional) + "."

    return Decision(
        urgency=urgency,
        protocol_id=primary,
        additional_protocol_ids=additional,
        action=" ".join(actions),
        notify=notify,
        matched_rules=list(matched.values()),
        findings=findings,
        possible_causes=list(causes.values()),
        clarifying_question=question,
        protocol_sources=sources,
        summary=summary,
        question_id=question_id,
        steps=steps,
        mission_procedures=procedures,
        missing_guidance=missing,
    )
