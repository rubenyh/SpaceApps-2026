"""State and dependencies at the parent graph boundary."""

from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime
from typing import Literal, TypedDict

from onboard_api.assistant.integrations import LLM, Retriever
from onboard_api.assistant.workflows.medical.state import EventSource, ReadingsProvider
from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse, OperationalEvent

Intent = Literal["medical", "clarify", "unsupported", "status"]


@dataclass(frozen=True, eq=False)  # eq=False: hashed by identity, one graph per object
class AssistantDeps:
    """Integration clients shared by every workflow (built once in the lifespan)."""

    llm: LLM
    retriever: Retriever
    readings: ReadingsProvider
    events: EventSource


class AssistantState(TypedDict, total=False):
    request: AssistantRequest
    now: datetime  # request start
    clock: Callable[[], datetime]  # onboard clock; workflows read it when loading readings
    events: list[OperationalEvent]  # active events, loaded once and passed to workflows
    intent: Intent
    distress: bool
    status_question: str  # "summary" | "missing" for the status workflow
    response: AssistantResponse
