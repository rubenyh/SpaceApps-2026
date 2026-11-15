"""Parent routing: medical / status / clarify / unsupported, plus the parent's nodes.

Deterministic (no LLM) so that an alarm message is never delayed by a classifier.
Psychological support is not an approved workflow: it routes to `unsupported`.
"""

import re
import unicodedata

from onboard_api.assistant.state import AssistantState
from onboard_api.assistant.status import status_question
from onboard_api.assistant.workflows.medical.interpret import interpret, is_sos
from onboard_api.assistant.workflows.medical.understand import case_for
from onboard_api.assistant.workflows.medical.state import EventSource
from onboard_api.schemas.assistant import AssistantResponse, Clarification

CLARIFY_QUESTION = (
    "Is your question about a symptom or discomfort you have now (you or another crew"
    " member), or about general health information from the onboard guides?"
)
UNSUPPORTED_REPLY = (
    "I can't help with that request. I can help with: current symptoms or discomfort"
    " for you or another crew member, cabin or radiation alerts, information about your"
    " readings (pulse, SpO₂, urine) and general health questions based on the onboard"
    " guides."
)
EMERGENCY_LINE = (
    "If there is an emergency or you feel in danger, follow the mission emergency"
    " procedure and call for help with the ship alarm."
)

# Stems matched on lowercase text without accents.
_PSYCH = (
    "psicolog", "ansiedad", "ansios", "estres", "triste", "deprim", "soledad",
    "me siento solo", "me siento sola", "salud mental", "emocional", "angustia",
    "animo", "panico", "llorar",
    "anxi", "stressed", "depress", "lonely", "mental health", "emotional", "panic",
)
_DISTRESS = (
    "emergencia", "auxilio", "socorro", "urgente", "peligro", "me muero",
    "no puedo mas", "suicid", "matarme", "hacerme dano", "panico",
    "emergency", "help me", "urgent", "danger", "dying", "kill myself", "hurt myself", "panic",
)
_VAGUE = ("hola", "ayuda", "ayudame", "duda", "pregunta", "consulta", "necesito",
          "hello", "hi", "hey", "help", "question", "need")


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
    # SOS, ship events and recognised symptoms go first to the medical alarm rules.
    if is_sos(request.message) or _relevant(active, request.astronaut_id) or interp.observations:
        return {**out, "intent": "medical"}
    # Quick questions about the person's own readings, even during a pending follow-up.
    if question := status_question(text):
        return {**out, "intent": "status", "status_question": question}
    if any(w in text for w in _PSYCH):
        return {**out, "intent": "unsupported"}
    if case_for(request):  # answer to a pending question: the same case continues
        return {**out, "intent": "medical"}
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
            clarification=Clarification(
                question_id="routing",
                question=CLARIFY_QUESTION,
                astronaut_id=state["request"].astronaut_id,
            ),
        )
    }


def respond_unsupported(state: AssistantState) -> dict:
    reply = f"{UNSUPPORTED_REPLY}\n\n{EMERGENCY_LINE}" if state.get("distress") else UNSUPPORTED_REPLY
    return {
        "response": AssistantResponse(reply=reply, workflow="unsupported", needs_clarification=False)
    }


def run_medical(state: AssistantState, medical_graph) -> dict:
    """Map parent state to the medical subgraph state and back, explicitly."""
    sub = {"request": state["request"], "now": state["now"], "events": state["events"]}
    if "clock" in state:
        sub["clock"] = state["clock"]
    out = medical_graph.invoke(sub)
    return {"response": out["response"]}
