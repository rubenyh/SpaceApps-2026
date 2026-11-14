"""Parent routing: medical / clarify / unsupported, plus the parent's nodes.

Deterministic (no LLM) so that an alarm message is never delayed by a classifier.
Psychological support is not an approved workflow: it routes to `unsupported`.
"""

import re
import unicodedata

from onboard_api.assistant.state import AssistantState
from onboard_api.assistant.workflows.medical.interpret import interpret
from onboard_api.assistant.workflows.medical.state import EventSource
from onboard_api.schemas.assistant import AssistantResponse

CLARIFY_QUESTION = (
    "¿Tu consulta es sobre un síntoma o malestar que tienes ahora (tú u otro"
    " tripulante), o sobre información general de salud de las guías a bordo?"
)
UNSUPPORTED_REPLY = (
    "No puedo ayudar con esa solicitud. Puedo ayudarte con: síntomas o malestares"
    " actuales tuyos o de otro tripulante, alertas de cabina o de radiación,"
    " información de tus lecturas (pulso, SpO₂, orina) y consultas generales de salud"
    " basadas en las guías a bordo."
)
EMERGENCY_LINE = (
    "Si hay una emergencia o te sientes en peligro, sigue el procedimiento de"
    " emergencia de la nave y contacta ahora al responsable médico a bordo."
)

# Stems matched on lowercase text without accents.
_PSYCH = (
    "psicolog", "ansiedad", "ansios", "estres", "triste", "deprim", "soledad",
    "me siento solo", "me siento sola", "salud mental", "emocional", "angustia",
    "animo", "panico", "llorar",
)
_DISTRESS = (
    "emergencia", "auxilio", "socorro", "urgente", "peligro", "me muero",
    "no puedo mas", "suicid", "matarme", "hacerme dano", "panico",
)
_VAGUE = ("hola", "ayuda", "ayudame", "duda", "pregunta", "consulta", "necesito")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _relevant(events, astronaut_id):
    return [e for e in events if not e.astronaut_ids or astronaut_id in e.astronaut_ids]


def select_intent(state: AssistantState, events: EventSource) -> dict:
    request = state["request"]
    active = [e for e in events.active_events(state["now"]) if e.status == "active"]
    text = _normalize(request.message)
    tokens = re.findall(r"\w+", text)
    distress = any(w in text for w in _DISTRESS)
    out = {"events": active, "distress": distress}

    interp = interpret(request)
    if _relevant(active, request.astronaut_id) or interp.observations:
        return {**out, "intent": "medical"}
    if any(w in text for w in _PSYCH):
        return {**out, "intent": "unsupported"}
    if interp.medical_signal:
        return {**out, "intent": "medical"}
    if not distress and (len(tokens) <= 2 or any(t in _VAGUE for t in tokens)):
        return {**out, "intent": "clarify"}
    return {**out, "intent": "unsupported"}


def route_after_intent(state: AssistantState) -> str:
    return state["intent"]


def respond_clarify(state: AssistantState) -> dict:
    return {
        "response": AssistantResponse(
            reply=CLARIFY_QUESTION,
            workflow="clarify",
            needs_clarification=True,
            clarifying_question=CLARIFY_QUESTION,
        )
    }


def respond_unsupported(state: AssistantState) -> dict:
    reply = f"{UNSUPPORTED_REPLY}\n\n{EMERGENCY_LINE}" if state.get("distress") else UNSUPPORTED_REPLY
    return {
        "response": AssistantResponse(reply=reply, workflow="unsupported", needs_clarification=False)
    }


def run_medical(state: AssistantState, medical_graph) -> dict:
    """Map parent state to the medical subgraph state and back, explicitly."""
    out = medical_graph.invoke(
        {"request": state["request"], "now": state["now"], "events": state["events"]}
    )
    return {"response": out["response"]}
