from collections.abc import Callable

from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse

# Anything that turns one console message into one assistant reply.
AssistantResponder = Callable[[AssistantRequest], AssistantResponse]

DISCLAIMER = (
    "Informational support only. Diagnosis and treatment decisions belong to"
    " qualified personnel."
)
