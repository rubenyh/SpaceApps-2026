"""Medical subgraph assembly (plan §3). Logic lives in nodes.py."""

from functools import partial

from langgraph.graph import END, START, StateGraph

from onboard_api.assistant.integrations import LLM, Retriever
from onboard_api.assistant.workflows.medical import nodes
from onboard_api.assistant.workflows.medical.state import (
    EventSource,
    MedicalState,
    ReadingsProvider,
)


def build_medical_graph(
    llm: LLM, retriever: Retriever, readings: ReadingsProvider, events: EventSource
):
    g = StateGraph(MedicalState)
    g.add_node("interpret", partial(nodes.interpret_report, events=events))
    g.add_node("evaluate_alarms", nodes.check_alarms)
    g.add_node("respond_alarm", partial(nodes.respond_alarm, readings=readings))
    # Qwen reads the turn only after the rules found no alarm; its observations are
    # checked against the alarm rules again before any slower dependency.
    g.add_node("understand", partial(nodes.understand_turn, llm=llm))
    g.add_node("recheck_alarms", nodes.check_alarms)
    g.add_node("load_context", partial(nodes.load_context, readings=readings))
    g.add_node("evaluate_case", nodes.assess_case)
    g.add_node("respond_clarify", nodes.respond_clarify)
    g.add_node("respond_out_of_coverage", nodes.respond_out_of_coverage)
    g.add_node("retrieve_guides", partial(nodes.retrieve_guides, retriever=retriever))
    g.add_node("compose_answer", partial(nodes.compose_answer, llm=llm))

    g.add_edge(START, "interpret")
    g.add_edge("interpret", "evaluate_alarms")
    g.add_conditional_edges(
        "evaluate_alarms", nodes.route_after_alarms, ["respond_alarm", "understand"]
    )
    g.add_edge("understand", "recheck_alarms")
    g.add_conditional_edges(
        "recheck_alarms", nodes.route_after_recheck, ["respond_alarm", "load_context"]
    )
    g.add_edge("load_context", "evaluate_case")
    g.add_conditional_edges(
        "evaluate_case",
        nodes.route_after_case,
        ["respond_clarify", "retrieve_guides", "respond_out_of_coverage"],
    )
    g.add_edge("retrieve_guides", "compose_answer")
    for terminal in ("respond_alarm", "respond_clarify", "respond_out_of_coverage", "compose_answer"):
        g.add_edge(terminal, END)
    return g.compile()
