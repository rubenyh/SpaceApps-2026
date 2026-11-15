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

_KIND = {"heart_rate": "Pulso", "spo2": "SpO₂"}
_STATUS = {"present": "presente", "absent": "ausente (negado)", "unknown": "desconocido (no se sabe)"}
_TEMPORALITY = {"current": "actual", "resolved": "ya cedió", "historical": "antecedente",
                "hypothetical": "hipotético"}
_ONSET = {"sudden": "súbito", "gradual": "gradual"}
_SEVERITY = {"mild": "leve", "moderate": "moderada", "severe": "intensa"}
_PERSISTENCE = {"ongoing": "persistente", "resolved": "resuelta", "recurrent": "recurrente"}
UNKNOWN = "desconocido"
NOT_SENT = (
    "Estado de envío: not_sent (pendiente). El asistente no transmite nada: cópialo y"
    " envíalo por el canal de la misión cuando haya enlace."
)


def _symptom_line(o: Observation) -> str:
    line = f"- {LABELS[o.symptom]}: {_STATUS[o.status]}"
    if o.status == "present":
        line += (
            f" ({_TEMPORALITY[o.temporality]}); inicio: {_ONSET.get(o.onset, UNKNOWN)};"
            f" intensidad: {_SEVERITY.get(o.severity, 'desconocida')};"
            f" evolución: {_PERSISTENCE.get(o.persistence, 'desconocida')}"
        )
        if o.subject == "other":
            line += "; reportado por otra persona"
    origin = f'texto "{o.evidence}"' if o.origin in ("text", "llm") else "entrada estructurada"
    return f"{line}. Origen: {origin}."


def _reading_lines(kinds: list[str], readings: ReadingsContext | None) -> list[str]:
    if readings is None or not readings.available:
        return ["- Lecturas no disponibles: no se pudo consultar el repositorio (estado desconocido)."]
    out = []
    for kind in kinds:
        label = _KIND.get(kind, kind)
        r = readings.latest.get(kind)
        if r is None:
            out.append(f"- {label}: sin lectura (valor desconocido).")
            continue
        value = f"{r.value:g}" if r.value is not None else (r.value_text or "")
        parts = [f"- {label}: {value} {r.unit}", f"medida {_iso(r.recorded_at)} (hace {r.age_seconds} s)",
                 f"calidad {r.quality}", f"fuente {r.source}"]
        if is_simulated_source(r.source):
            parts.append("SIMULADA, no es una medición real")
        if r.stale:
            parts.append("VIEJA, no refleja el estado actual")
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
    reporter = request.reported_by or "la propia persona"

    lines = [
        "INFORME DE CASO MÉDICO (generado a bordo; soporte informativo, no es un diagnóstico)",
        f"Generado: {_iso(now)}",
        f"Astronauta: {request.astronaut_id or UNKNOWN} · Reporta: {reporter}",
        NOT_SENT,
        "",
        f"Urgencia (reglas): {urgency or UNKNOWN}",
        f"Acción recomendada: {action or 'ninguna definida por las fichas'}",
    ]
    for p in decision.mission_procedures if decision else []:
        lines.append(f"Procedimiento de la misión: {p.title} ({'cargado' if p.loaded else 'NO cargado en el asistente'})")

    lines += ["", "Síntomas reportados:"]
    lines += [_symptom_line(o) for o in observations] or ["- Ninguno identificado en el mensaje."]

    relevant = _relevant_events(events, request.astronaut_id)
    if relevant:
        lines += ["", "Eventos de la nave:"] + [f"- {event_finding(e).detail}" for e in relevant]

    lines += ["", "Lecturas pertinentes:"] + _reading_lines(kinds, readings)

    missing: list[str] = []
    for o in observations:
        if o.status == "present" and o.temporality in ("current", "resolved"):
            if o.onset is None:
                missing.append(f"Inicio de {LABELS[o.symptom].lower()}: desconocido.")
            if o.severity is None:
                missing.append(f"Intensidad de {LABELS[o.symptom].lower()}: desconocida.")
    missing += notices
    if decision:
        missing += decision.missing_guidance
    lines += ["", "Información que falta:"] + ([f"- {m}" for m in dict.fromkeys(missing)] or ["- Nada identificado."])

    if decision and decision.matched_rules:
        rules = ", ".join(f"{r.rule_id} ({r.protocol_id}@{r.protocol_version})" for r in decision.matched_rules)
        lines += ["", f"Reglas aplicadas: {rules}"]
    return CaseReport(text="\n".join(lines))
