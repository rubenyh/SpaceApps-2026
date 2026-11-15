"""Copyable case report. Deterministic: built only from the case, readings, events and
the rules' decision; the LLM never writes it. Nothing here transmits anything."""

import re
from datetime import datetime
from uuid import uuid4

from onboard_api.assistant.workflows.medical.context import snapshot
from onboard_api.assistant.workflows.medical.protocols import load_catalog
from onboard_api.assistant.workflows.medical.state import (
    Decision,
    Interpretation,
    Observation,
    ReadingsContext,
)
from onboard_api.assistant.workflows.medical.triage import (
    LABELS,
    PERTINENT_READINGS,
    _iso,
    event_finding,
    _relevant_events,
)
from onboard_api.schemas.assistant import (
    AssessmentSummary,
    AssistantRequest,
    CaseReport,
    OperationalEvent,
)
from onboard_api.schemas.readings import is_simulated_source

_KIND = {"heart_rate": "Pulse", "spo2": "SpO₂"}
_STATUS = {"present": "present", "absent": "absent (denied)", "unknown": "unknown (not known)"}
_TEMPORALITY = {"current": "current", "resolved": "already eased", "historical": "past history",
                "hypothetical": "hypothetical"}
_ONSET = {"sudden": "sudden", "gradual": "gradual"}
_SEVERITY = {"mild": "mild", "moderate": "moderate", "severe": "severe"}
_PERSISTENCE = {"ongoing": "persistent", "resolved": "resolved", "recurrent": "recurrent"}
UNKNOWN = "unknown"
URGENCY_LABELS = {"immediate": "Immediate", "review_required": "Review required",
                  "undetermined": "Undetermined", "informational": "Informational"}
_ESCALATION = re.compile(r"emergenc|escalat", re.IGNORECASE)


def _symptom_line(o: Observation) -> str:
    line = f"- {LABELS[o.symptom]}: {_STATUS[o.status]}"
    if o.status == "present":
        line += (
            f" ({_TEMPORALITY[o.temporality]}); onset: {_ONSET.get(o.onset, UNKNOWN)};"
            f" intensity: {_SEVERITY.get(o.severity, UNKNOWN)};"
            f" course: {_PERSISTENCE.get(o.persistence, UNKNOWN)}"
        )
        if o.subject == "other":
            line += "; reported by another person"
    origin = f'text "{o.evidence}"' if o.origin in ("text", "llm") else "structured input"
    return f"{line}. Origin: {origin}."


def _reading_lines(kinds: list[str], readings: ReadingsContext | None) -> list[str]:
    if readings is None or not readings.available:
        return ["- Readings unavailable: the repository could not be queried (status unknown)."]
    out = []
    for kind in kinds:
        label = _KIND.get(kind, kind)
        r = readings.latest.get(kind)
        if r is None:
            out.append(f"- {label}: no reading (value unknown).")
            continue
        value = f"{r.value:g}" if r.value is not None else (r.value_text or "")
        parts = [f"- {label}: {value} {r.unit}", f"measured {_iso(r.recorded_at)} ({r.age_seconds} s ago)",
                 f"quality {r.quality}", f"source {r.source}"]
        if is_simulated_source(r.source):
            parts.append("SIMULATED, not a real measurement")
        if r.freshness == "future":
            parts.append("capture time AHEAD of the onboard clock, not current")
        elif r.stale:
            parts.append("OLD, does not reflect the current state")
        out.append(" · ".join(parts) + ".")
    return out


def build_report(
    request: AssistantRequest,
    now: datetime,
    interp: Interpretation,
    events: list[OperationalEvent],
    readings: ReadingsContext | None,
    decision: Decision | None,
    urgency: str | None,
    action: str | None,
    notices: list[str],
) -> CaseReport:
    pids = [decision.protocol_id, *decision.additional_protocol_ids] if decision and decision.protocol_id else []
    kinds = list(dict.fromkeys(k for p in pids for k in PERTINENT_READINGS.get(p, ()))) or ["spo2", "heart_rate"]
    observations = [o for o in interp.observations if o.temporality != "hypothetical"]
    reporter = request.reported_by or "the person themselves"

    lines = [
        "MEDICAL CASE REPORT (generated on board; informational support, not a diagnosis)",
        f"Generated: {_iso(now)}",
        f"Astronaut: {request.astronaut_id or UNKNOWN} · Reported by: {reporter}",
        "",
        f"Urgency (rules): {urgency or UNKNOWN}",
        f"Recommended action: {action or 'none defined by the cards'}",
    ]
    for p in decision.mission_procedures if decision else []:
        lines.append(f"Mission procedure: {p.title} ({'loaded' if p.loaded else 'NOT loaded in the assistant'})")

    lines += ["", "Reported symptoms:"]
    lines += [_symptom_line(o) for o in observations] or ["- None identified in the message."]

    relevant = _relevant_events(events, request.astronaut_id)
    if relevant:
        lines += ["", "Ship events:"] + [f"- {event_finding(e).detail}" for e in relevant]

    lines += ["", "Relevant readings:"] + _reading_lines(kinds, readings)

    missing: list[str] = []
    for o in observations:
        if o.status == "present" and o.temporality in ("current", "resolved"):
            if o.onset is None:
                missing.append(f"Onset of {LABELS[o.symptom].lower()}: unknown.")
            if o.severity is None:
                missing.append(f"Intensity of {LABELS[o.symptom].lower()}: unknown.")
    missing += notices
    if decision:
        missing += decision.missing_guidance
    lines += ["", "Missing information:"] + ([f"- {m}" for m in dict.fromkeys(missing)] or ["- Nothing identified."])

    if decision and decision.matched_rules:
        rules = ", ".join(f"{r.rule_id} ({r.protocol_id}@{r.protocol_version})" for r in decision.matched_rules)
        lines += ["", f"Rules applied: {rules}"]
    pertinent = snapshot(readings, kinds) if readings is not None and readings.available else []
    return CaseReport(id=str(uuid4()), readings=pertinent, text="\n".join(lines))


def _short(text: str) -> str:
    """"Dizziness without neurologic signs: limit movement and monitor." ->
    "Limit movement and monitor": first sentence of the clause after the label."""
    clause = text.split(": ", 1)[-1].split(". ", 1)[0].strip().rstrip(".")
    return clause[:1].upper() + clause[1:]


def assessment_summary(
    decision: Decision | None, urgency: str, action: str | None,
    interp: Interpretation | None, events: list[OperationalEvent], astronaut_id: str | None,
    sos: bool,
) -> AssessmentSummary:
    """Glanceable head built from the rules and the card text only."""
    present = [o for o in (interp.observations if interp else [])
               if o.status == "present" and o.temporality in ("current", "resolved")]
    relevant = _relevant_events(events, astronaut_id)
    if sos:
        reported = "SOS reported"
    elif present:
        reported = f"{LABELS[present[0].symptom]} reported"
    elif relevant:
        reported = "Radiation alert reported" if relevant[0].type == "radiation" else "Cabin alarm reported"
    else:
        reported = "Symptom reported"

    card_action = None
    escalation: list[str] = []
    if decision and decision.protocol_id:
        card = load_catalog()[decision.protocol_id]
        lead = [a for a in card.actions.values() if a.text in (decision.action or "")]
        card_action = lead[0].text if lead else None
        escalation = [t for a in lead for t in (*(st.text for st in a.steps), *a.notify)
                      if _ESCALATION.search(t)]
    text = action if sos else (card_action or action)
    return AssessmentSummary(
        urgency=urgency, urgency_label=URGENCY_LABELS[urgency], reported=reported,
        action=_short(text) if text else None, escalation=list(dict.fromkeys(escalation)),
    )
