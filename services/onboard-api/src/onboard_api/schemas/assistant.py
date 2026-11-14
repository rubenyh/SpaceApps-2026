from typing import Literal

from pydantic import BaseModel, Field

AssistantWorkflow = Literal["medical", "clarify", "unsupported"]


class GuideSource(BaseModel):
    id: str
    title: str


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1)
    astronaut_id: str | None = None


class AssistantResponse(BaseModel):
    """Same shape for every workflow. New workflows add a `workflow` value."""

    reply: str
    workflow: AssistantWorkflow
    needs_clarification: bool
    sources: list[GuideSource] = []
    data_notices: list[str] = []
    disclaimer: str | None = None
