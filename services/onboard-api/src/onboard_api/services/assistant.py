from collections.abc import Callable

from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse

# Anything that turns one console message into one assistant reply.
AssistantResponder = Callable[[AssistantRequest], AssistantResponse]

DISCLAIMER = (
    "Soporte informativo únicamente. El diagnóstico y las decisiones de "
    "tratamiento corresponden a personal cualificado."
)
