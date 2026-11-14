from collections.abc import Callable

from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse

# Anything that turns one console message into one assistant reply.
AssistantResponder = Callable[[AssistantRequest], AssistantResponse]

STUB_REPLY = "El asistente todavía no está conectado. Esta es una respuesta de prueba."
STUB_DATA_NOTICE = "Respuesta de prueba: el asistente aún no consulta lecturas ni guías."
DISCLAIMER = (
    "Soporte informativo únicamente. El diagnóstico y las decisiones de "
    "tratamiento corresponden a personal cualificado."
)


def stub_responder(request: AssistantRequest) -> AssistantResponse:
    """Placeholder until the LangGraph assistant is connected. Ignores the input."""
    return AssistantResponse(
        reply=STUB_REPLY,
        workflow="unsupported",
        needs_clarification=False,
        sources=[],
        data_notices=[STUB_DATA_NOTICE],
        disclaimer=DISCLAIMER,
    )
