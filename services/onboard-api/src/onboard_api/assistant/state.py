"""State and dependencies at the parent graph boundary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from onboard_api.assistant.integrations import LLM, Retriever
from onboard_api.assistant.workflows.medical.state import EventSource, ReadingsProvider
from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse, OperationalEvent

Intent = Literal["medical", "clarify", "unsupported"]


@dataclass(frozen=True, eq=False)  # eq=False: hashed by identity, one graph per object
class AssistantDeps:
    """Integration clients shared by every workflow (built once in the lifespan)."""

    llm: LLM
    retriever: Retriever
    readings: ReadingsProvider
    events: EventSource


class AssistantState(TypedDict, total=False):
    request: AssistantRequest
    now: datetime
    events: list[OperationalEvent]  # active events, loaded once and passed to workflows
    intent: Intent
    distress: bool
    response: AssistantResponse
