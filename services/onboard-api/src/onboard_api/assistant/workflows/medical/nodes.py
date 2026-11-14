"""Medical workflow nodes. Dependencies are bound with functools.partial in graph.py.

Rules decide urgency, action and causes (triage.py). Retrieval and the LLM only
add an explanation; any failure there becomes a data notice plus card text.
"""

import re

from onboard_api.assistant.integrations import LLM, GuideChunk, Retriever
from onboard_api.assistant.workflows.medical import prompts
from onboard_api.assistant.workflows.medical.interpret import interpret
from onboard_api.assistant.workflows.medical.protocols import load_catalog
from onboard_api.assistant.workflows.medical.state import (
    Decision,
    EventSource,
    MedicalState,
    ReadingsContext,
    ReadingsProvider,
)
from onboard_api.assistant.workflows.medical.triage import (
    decide,
    evaluate_alarms,
    evaluate_case,
    select_route,
)
from onboard_api.schemas.assistant import AssistantResponse, GuideSource, Urgency

_CITATION = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _response(
    state: MedicalState,
    reply: str,
    decision: Decision | None = None,
    sources: list[GuideSource] | None = None,
    urgency: Urgency | None = None,
    action: str | None = None,
    notify: list[str] | None = None,
) -> dict:
    d = decision
    return {
        "response": AssistantResponse(
            reply=reply,
            workflow="medical",
            needs_clarification=state.get("route") == "clarify",
            sources=sources if sources is not None else (d.protocol_sources if d else []),
            data_notices=list(state.get("notices", [])),
            disclaimer=prompts.DISCLAIMER,
            urgency=urgency or (d.urgency if d else None),
            action=action or (d.action if d else None),
            notify=notify or (d.notify if d else []),
            protocol_id=d.protocol_id if d else None,
            additional_protocol_ids=d.additional_protocol_ids if d else [],
            matched_rules=d.matched_rules if d else [],
            findings=d.findings if d else [],
            possible_causes=d.possible_causes if d else [],
            clarifying_question=d.clarifying_question if d else None,
        )
    }


# --- Alarm branch: local cards only, no SQLite / ChromaDB / Ollama. ---


def interpret_report(state: MedicalState, events: EventSource) -> dict:
    found = state["events"] if "events" in state else events.active_events(state["now"])
    return {"interpretation": interpret(state["request"]), "events": found, "notices": []}


def check_alarms(state: MedicalState) -> dict:
    hits = evaluate_alarms(
        state["interpretation"], state["events"], state["request"].astronaut_id
    )
    return {"alarm_hits": hits}


def route_after_alarms(state: MedicalState) -> str:
    return "respond_alarm" if state["alarm_hits"] else "load_context"


def respond_alarm(state: MedicalState) -> dict:
    decision = decide(state["alarm_hits"], load_catalog(), None)
    state = {**state, "notices": [*state.get("notices", []), prompts.ALARM_NOTICE]}
    return {"route": "alarm", "decision": decision, **_response(state, decision.summary, decision)}


# --- Non-alarm branch. ---


def load_context(state: MedicalState, readings: ReadingsProvider) -> dict:
    try:
        ctx = readings.load(state["request"].astronaut_id, state["now"])
    except Exception:  # providers should not raise; never let one break the reply
        ctx = ReadingsContext(available=False, warnings=[prompts.NOTICE_READINGS_FAILED])
    return {"readings": ctx, "notices": [*state.get("notices", []), *ctx.warnings]}


def assess_case(state: MedicalState) -> dict:
    interp, readings = state["interpretation"], state["readings"]
    hits = evaluate_case(interp, state["events"], readings)
    route = select_route(interp, state["alarm_hits"], hits)
    out: dict = {"case_hits": hits, "route": route}
    if hits:
        out["decision"] = decide(hits, load_catalog(), readings)
    return out


def route_after_case(state: MedicalState) -> str:
    return {
        "clarify": "respond_clarify",
        "assessment": "retrieve_guides",
        "educational": "retrieve_guides",
    }.get(state["route"], "respond_out_of_coverage")


def respond_clarify(state: MedicalState) -> dict:
    d = state["decision"]
    question = d.clarifying_question
    reply = d.summary if not question or question in d.summary else f"{d.summary}\n\n{question}"
    return _response(state, reply.strip(), d)


def respond_out_of_coverage(state: MedicalState) -> dict:
    return _response(
        state,
        f"{prompts.OUT_OF_COVERAGE_ACTION}\n\n{prompts.OUT_OF_COVERAGE_REPLY}",
        urgency="review_required",
        action=prompts.OUT_OF_COVERAGE_ACTION,
        notify=[prompts.MEDICAL_OFFICER],
        sources=[],
    )


def _card(state: MedicalState):
    """Primary card of the decision, or the card the educational question is about."""
    decision = state.get("decision")
    card_id = decision.protocol_id if decision else state["interpretation"].topic_hint
    return load_catalog().get(card_id) if card_id else None


def retrieve_guides(state: MedicalState, retriever: Retriever) -> dict:
    card = _card(state)
    # Assessments query by card topic (no personal text); educational requests
    # use the question. Nothing is stored in ChromaDB.
    query = card.title if card and state.get("decision") else state["request"].message
    topics = list(card.guide_topics) if card and card.guide_topics else None
    notices = list(state.get("notices", []))
    try:
        guides = list(retriever.search(query, k=3, topics=topics, language="es"))
    except Exception:
        guides = []
        notices.append(prompts.NOTICE_GUIDES_FAILED)
    if not guides and prompts.NOTICE_GUIDES_FAILED not in notices:
        notices.append(prompts.NOTICE_NO_GUIDES)
    return {"guides": guides, "notices": notices}


def valid_draft(draft: str, chunks: list[GuideChunk], context: str) -> bool:
    """Non-empty, cites only provided chunks, and every number appears in the context."""
    if not draft.strip():
        return False
    if any(not 1 <= int(n) <= len(chunks) for n in _CITATION.findall(draft)):
        return False
    return all(n in context for n in _NUMBER.findall(_CITATION.sub("", draft)))


def _chunk_source(c: GuideChunk) -> GuideSource:
    return GuideSource(id=c.chunk_id, title=c.title, section=c.section, url=c.url, kind="guide")


def compose_answer(state: MedicalState, llm: LLM) -> dict:
    decision: Decision | None = state.get("decision")
    chunks: list[GuideChunk] = state.get("guides", [])
    notices = list(state.get("notices", []))
    educational = decision is None

    if educational and not chunks:
        return _response(
            {**state, "notices": notices},
            prompts.EDUCATIONAL_ABSTAIN,
            urgency="informational",
            sources=[],
        )

    draft = None
    if chunks:  # without chunks the card text already says everything we can back
        card = _card(state)
        user = prompts.build_user_prompt(
            state["request"].message,
            decision.action if decision else None,
            card.summary if card else None,
            [f.detail for f in decision.findings] if decision else [],
            notices,
            chunks,
        )
        try:
            draft = llm.chat(prompts.SYSTEM, user).strip()
        except Exception:
            notices.append(prompts.NOTICE_LLM_FAILED)
        else:
            if not valid_draft(draft, chunks, prompts.SYSTEM + user):
                draft = None
                notices.append(prompts.NOTICE_DRAFT_REJECTED)

    card_sources = decision.protocol_sources if decision else []
    if draft:
        action = decision.action if decision else None
        reply = f"{action}\n\n{draft}" if action else draft
        sources = [*card_sources, *map(_chunk_source, chunks)]
    elif decision:
        reply, sources = decision.summary, list(card_sources)
    else:
        reply, sources = prompts.guide_excerpt(chunks[0]), [_chunk_source(chunks[0])]

    return _response(
        {**state, "notices": notices},
        reply,
        decision,
        sources=sources,
        urgency=None if decision else "informational",
    )
