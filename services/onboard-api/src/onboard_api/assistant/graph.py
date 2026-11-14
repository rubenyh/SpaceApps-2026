"""Parent graph assembly: one entry point, routed to workflow subgraphs."""

from datetime import datetime
from functools import lru_cache, partial

from langgraph.graph import END, START, StateGraph

from onboard_api.assistant import routing
from onboard_api.assistant.state import AssistantDeps, AssistantState
from onboard_api.assistant.workflows.medical.graph import build_medical_graph
from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse


@lru_cache(maxsize=8)  # compiled once per AssistantDeps object (identity hash)
def build_assistant_graph(deps: AssistantDeps):
    medical = build_medical_graph(deps.llm, deps.retriever, deps.readings, deps.events)
    g = StateGraph(AssistantState)
    g.add_node("select_intent", partial(routing.select_intent, events=deps.events))
    g.add_node("medical", partial(routing.run_medical, medical_graph=medical))
    g.add_node("clarify", routing.respond_clarify)
    g.add_node("unsupported", routing.respond_unsupported)
    g.add_edge(START, "select_intent")
    g.add_conditional_edges(
        "select_intent", routing.route_after_intent, ["medical", "clarify", "unsupported"]
    )
    for node in ("medical", "clarify", "unsupported"):
        g.add_edge(node, END)
    return g.compile()


def respond(graph, request: AssistantRequest, now: datetime) -> AssistantResponse:
    return graph.invoke({"request": request, "now": now})["response"]
