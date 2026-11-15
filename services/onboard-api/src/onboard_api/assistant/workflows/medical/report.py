"""Copyable case report. Deterministic: built only from the case, readings, events and
the rules' decision; the LLM never writes it. Nothing here transmits anything."""

from datetime import datetime

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
from onboard_api.schemas.assistant import AssistantRequest, CaseReport, OperationalEvent
from onboard_api.schemas.readings import is_simulated_source

_KIND = {"heart_rate": "Pulse", "spo2": "SpO₂"}
_STATUS = {"present": "present", "absent": "absent (denied)", "unknown": "unknown (not known)"}
_TEMPORALITY = {"current": "current", "resolved": "already eased", "historical": "past history",
                "hypothetical": "hypothetical"}
_ONSET = {"sudden": "sudden", "gradual": "gradual"}
_SEVERITY = {"mild": "mild", "moderate": "moderate", "severe": "severe"}
_PERSISTENCE = {"ongoing": "persistent", "resolved": "resolved", "recurrent": "recurrent"}
UNKNOWN = "unknown"
NOT_SENT = (
    "Send status: not_sent (pending). The assistant transmits nothing: copy it and send it"
    " through the mission channel when the link is up."
)


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
        if r.stale:
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
        NOT_SENT,
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
    return CaseReport(text="\n".join(lines))
