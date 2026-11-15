"""Medical workflow nodes. Dependencies are bound with functools.partial in graph.py.

Rules decide urgency, action and causes (triage.py). Retrieval and the LLM only
add an explanation; any failure there becomes a data notice plus card text.
"""

import re

from onboard_api.assistant.integrations import LLM, EmbeddingUnavailable, GuideChunk, Retriever
from onboard_api.assistant.workflows.medical import prompts
from onboard_api.assistant.workflows.medical import understand
from onboard_api.assistant.workflows.medical.interpret import interpret, is_sos
from onboard_api.assistant.workflows.medical.protocols import load_catalog
from onboard_api.assistant.workflows.medical.report import build_report
from onboard_api.assistant.workflows.medical.state import (
    Decision,
    EventSource,
    MedicalState,
    ReadingsContext,
    ReadingsProvider,
)
from onboard_api.assistant.workflows.medical.triage import (
    GENERIC_CLARIFYING_QUESTION,
    PERTINENT_READINGS,
    decide,
    evaluate_alarms,
    evaluate_case,
    select_route,
)
from onboard_api.schemas.assistant import (
    AssistantResponse,
    Clarification,
    Finding,
    GuideSource,
    MissionProcedure,
    Urgency,
)

_CITATION = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# ponytail: keyword screen, not a semantic check; the card action is shown first anyway.
# Rejects transmission or notification claims, de-escalation, an onboard clinician that
# does not exist, and absence claims (unknown stays unknown; absent comes from the report).
_UNSAFE = re.compile(
    r"envi[aéó]|transmit|avis[eéó]|avisad|notific|inform[eéó]\b|contact[eéó]|se (le )?(comunic|llam)"
    r"|no es urgente|no hace falta|no (es|hace) necesario|no (es|parece) grave|no te preocupes"
    r"|m[eé]dico|doctor|cl[ií]nico|enfermer"
    r"|descart|no (tienes|tiene|presentas|presenta|hay signos|hay se[nñ]ales)|ausencia de|sin signos"
    # English drafts (the prompt asks for English).
    r"|\b(sent|transmitt\w*|notif\w*|informed|alerted|contacted|reported to)\b"
    r"|not (urgent|serious|necessary|needed)|no need|don'?t worry|nothing to worry"
    r"|physician|nurse|clinic(al|ian)|medical (officer|staff)"
    r"|rul(e|ed|ing) out|you (do not|don'?t) have|(is|are) absent|absence of|no (signs?|evidence) of",
    re.IGNORECASE,
)


def _response(
    state: MedicalState,
    reply: str,
    decision: Decision | None = None,
    sources: list[GuideSource] | None = None,
    urgency: Urgency | None = None,
    action: str | None = None,
    notify: list[str] | None = None,
    clarification: Clarification | None = None,
    procedures: list[MissionProcedure] | None = None,
    always_report: bool = False,
) -> dict:
    d = decision
    urgency = urgency or (d.urgency if d else None)
    action = action or (d.action if d else None)
    interp = state.get("interpretation")
    report = None
    if always_report or d or (interp and any(o.temporality != "hypothetical" for o in interp.observations)):
        report = build_report(
            state["request"], state["now"], interp, state.get("events", []),
            state.get("readings"), d, urgency, action,
            [n for n in state.get("notices", []) if n not in prompts.ASSISTANT_NOTICES],
        )
    return {
        "response": AssistantResponse(
            reply=reply,
            workflow="medical",
            needs_clarification=state.get("route") == "clarify",
            sources=sources if sources is not None else (d.protocol_sources if d else []),
            data_notices=list(state.get("notices", [])),
            disclaimer=prompts.DISCLAIMER,
            urgency=urgency,
            action=action,
            notify=notify or (d.notify if d else []),
            steps=d.steps if d else [],
            mission_procedures=procedures or (d.mission_procedures if d else []),
            missing_guidance=d.missing_guidance if d else [],
            report=report,
            protocol_id=d.protocol_id if d else None,
            additional_protocol_ids=d.additional_protocol_ids if d else [],
            matched_rules=d.matched_rules if d else [],
            findings=d.findings if d else [],
            possible_causes=d.possible_causes if d else [],
            clarifying_question=d.clarifying_question if d else None,
            clarification=clarification,
        )
    }


# --- Alarm branch: local cards only, no SQLite / ChromaDB / Ollama. ---


def interpret_report(state: MedicalState, events: EventSource) -> dict:
    """Rules on the new message, merged with the open case echoed by the console."""
    request = state["request"]
    found = state["events"] if "events" in state else events.active_events(state["now"])
    case = understand.case_for(request)
    previous = [understand.to_observation(o) for o in case.observations] if case else []
    base = interpret(request)
    if case:  # "sí, un poco" or "empezó de repente" read against the pending question
        subject = understand.subject_of(request, previous)
        base = understand.answer_turn(base, request.message, case, previous, subject)
    return {
        "interpretation": understand.merge_case(base, previous),
        "events": found,
        "clarification": case,
        "sos": is_sos(request.message),
        "notices": [],
    }


def check_alarms(state: MedicalState) -> dict:
    hits = evaluate_alarms(
        state["interpretation"], state["events"], state["request"].astronaut_id
    )
    return {"alarm_hits": hits}


def route_after_alarms(state: MedicalState) -> str:
    return "respond_alarm" if state["alarm_hits"] or state.get("sos") else "understand"


def route_after_recheck(state: MedicalState) -> str:
    return "respond_alarm" if state["alarm_hits"] else "load_context"


def _with_sos(decision: Decision | None) -> Decision:
    """SOS leads the action; card alarms found in the same turn are kept."""
    finding = Finding(kind="event", detail=prompts.SOS_FINDING, source="report")
    emergency = MissionProcedure(title=prompts.EMERGENCY_PROCEDURE)
    if decision is None:
        return Decision("immediate", None, [], prompts.SOS_ACTION, list(prompts.NOTIFY_EMERGENCY), [],
                        [finding], [], None, [], prompts.SOS_ACTION, mission_procedures=[emergency])
    decision.action = f"{prompts.SOS_ACTION} {decision.action}"
    decision.summary = f"{prompts.SOS_ACTION}\n{decision.summary}"
    decision.notify = list(dict.fromkeys([*prompts.NOTIFY_EMERGENCY, *decision.notify]))
    decision.findings = [finding, *decision.findings]
    if all(p.title != emergency.title for p in decision.mission_procedures):
        decision.mission_procedures = [emergency, *decision.mission_procedures]
    return decision


def respond_alarm(state: MedicalState, readings: ReadingsProvider) -> dict:
    """The alarm is decided from the cards, events and request. Readings (local SQLite,
    never Ollama/ChromaDB) only add evidence and the report; they never change urgency."""
    hits = state["alarm_hits"]
    ctx = _safe_load(readings, state)
    decision = decide(hits, load_catalog(), ctx) if hits else None
    if state.get("sos"):
        decision = _with_sos(decision)
    notices = [*state.get("notices", []), prompts.ALARM_NOTICE, *_reading_notices(ctx, decision)]
    state = {**state, "readings": ctx, "notices": notices}
    return {"route": "alarm", "decision": decision, "readings": ctx,
            **_response(state, decision.summary, decision)}


# --- Local interpreter (Qwen), only once no alarm is pending. ---


def understand_turn(state: MedicalState, llm: LLM) -> dict:
    interp, case, request = state["interpretation"], state.get("clarification"), state["request"]
    if interp.request_kind == "educational":
        return {}  # general question: nothing to extract, and no symptom to invent
    reading = understand.read_turn(
        llm, request.message, case.question if case else None, interp.observations
    )
    if reading is None:  # Ollama down, slow or invalid output: the rules alone decide
        return {}
    subject = understand.subject_of(request, interp.observations)
    extra, uncovered = understand.accept(
        reading, request, case.question_id if case else None, subject
    )
    return {"interpretation": understand.add_llm(interp, extra, uncovered)}


# --- Non-alarm branch. ---


def _safe_load(readings: ReadingsProvider, state: MedicalState) -> ReadingsContext:
    try:
        return readings.load(state["request"].astronaut_id, state["now"])
    except Exception:  # providers should not raise; never let one break the reply
        return ReadingsContext(available=False, warnings=[prompts.NOTICE_READINGS_FAILED])


def load_context(state: MedicalState, readings: ReadingsProvider) -> dict:
    return {"readings": _safe_load(readings, state)}


def _reading_notices(readings: ReadingsContext, decision: Decision | None) -> list[str]:
    """Reading warnings that matter for the decision's cards; none without a decision."""
    pids = [decision.protocol_id, *decision.additional_protocol_ids] if decision and decision.protocol_id else []
    kinds = {k for p in pids for k in PERTINENT_READINGS.get(p, ())}
    if not kinds:
        return []
    owned = {w for ws in readings.kind_warnings.values() for w in ws}
    pertinent = {w for k in kinds for w in readings.kind_warnings.get(k, [])}
    return [w for w in readings.warnings if w not in owned or w in pertinent]


def assess_case(state: MedicalState) -> dict:
    interp, readings = state["interpretation"], state["readings"]
    hits = evaluate_case(interp, state["events"], readings)
    route = select_route(interp, state["alarm_hits"], hits)
    case = state.get("clarification")
    if route == "clarify" and not hits and case and case.question_id == "symptom":
        route = "out_of_coverage"  # asked what the person feels and still no symptom we cover
    decision = decide(hits, load_catalog(), readings) if hits else None
    out: dict = {
        "case_hits": hits,
        "route": route,
        "notices": [*state.get("notices", []), *_reading_notices(readings, decision)],
    }
    if decision:
        out["decision"] = decision
    return out


def route_after_case(state: MedicalState) -> str:
    return {
        "clarify": "respond_clarify",
        "assessment": "retrieve_guides",
        "educational": "retrieve_guides",
    }.get(state["route"], "respond_out_of_coverage")


def _pending(state: MedicalState, question_id: str, question: str) -> Clarification:
    """Open case returned to the console, which sends it back with the answer."""
    return Clarification(
        question_id=question_id,
        question=question,
        astronaut_id=state["request"].astronaut_id,
        observations=[understand.to_case(o) for o in state["interpretation"].observations],
    )


def respond_clarify(state: MedicalState) -> dict:
    d = state.get("decision")
    if d is None:  # report with no concrete symptom yet: ask what the person feels
        q = GENERIC_CLARIFYING_QUESTION
        out = _response(state, q, urgency="undetermined", sources=[],
                        clarification=_pending(state, "symptom", q))
        out["response"].clarifying_question = q
        return out
    question = d.clarifying_question
    reply = d.summary if not question or question in d.summary else f"{d.summary}\n\n{question}"
    pending = _pending(state, d.question_id, question) if question and d.question_id else None
    return _response(state, reply.strip(), d, clarification=pending)


def respond_out_of_coverage(state: MedicalState) -> dict:
    out = _response(
        state,
        f"{prompts.OUT_OF_COVERAGE_ACTION}\n\n{prompts.OUT_OF_COVERAGE_REPLY}",
        urgency="review_required",
        action=prompts.OUT_OF_COVERAGE_ACTION,
        notify=list(prompts.NOTIFY_GROUND),
        sources=[],
        procedures=[MissionProcedure(title=prompts.MEDICAL_PROCEDURE)],
        always_report=True,
    )
    out["response"].missing_guidance = [prompts.OUT_OF_COVERAGE_MISSING]
    return out


def _card(state: MedicalState):
    """Primary card of the decision, or the card the educational question is about."""
    decision = state.get("decision")
    card_id = decision.protocol_id if decision else state["interpretation"].topic_hint
    return load_catalog().get(card_id) if card_id else None


def retrieve_guides(state: MedicalState, retriever: Retriever) -> dict:
    card = _card(state)
    # Query by card title (topic), never by personal text. Only an educational
    # question with no recognised topic falls back to the message itself.
    # Nothing is stored in ChromaDB.
    query = card.title if card else state["request"].message
    topics = list(card.guide_topics) if card and card.guide_topics else None
    notices = list(state.get("notices", []))
    guides, failure = [], None
    try:
        # English replies: Spanish fallbacks from the retriever are dropped.
        guides = [g for g in retriever.search(query, k=3, topics=topics, language="en")
                  if g.language == "en"]
    except EmbeddingUnavailable:
        failure = prompts.NOTICE_EMBEDDING_FAILED
    except Exception:
        failure = prompts.NOTICE_GUIDES_FAILED
    if failure:
        notices.append(failure)
    elif not guides:
        notices.append(prompts.NOTICE_NO_GUIDES)
    return {"guides": guides, "notices": notices}


def valid_draft(draft: str, chunks: list[GuideChunk], grounding: str) -> bool:
    """Non-empty, cites only provided chunks, every number is one of the numbers in
    the grounding text (card, findings, notices, chunks; not the system prompt),
    and no transmission or de-escalation claim."""
    if not draft.strip() or _UNSAFE.search(draft):
        return False
    if any(not 1 <= int(n) <= len(chunks) for n in _CITATION.findall(draft)):
        return False
    allowed = set(_NUMBER.findall(grounding))
    return set(_NUMBER.findall(_CITATION.sub("", draft))) <= allowed


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
        report = build_report(state["request"], state["now"], state["interpretation"],
                              state.get("events", []), state.get("readings"), decision,
                              decision.urgency, decision.action, notices) if decision else None
        user = prompts.build_user_prompt(
            card.title if card else None,
            decision.action if decision else None,
            card.summary if card else None,
            [f.detail for f in decision.findings] if decision else [],
            notices,
            chunks,
            report.text if report else None,
        )
        try:
            draft = llm.chat(prompts.SYSTEM, user).strip()
        except Exception:
            notices.append(prompts.NOTICE_LLM_FAILED)
        else:
            if not valid_draft(draft, chunks, user):
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
