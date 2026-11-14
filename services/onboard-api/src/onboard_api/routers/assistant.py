from fastapi import APIRouter

from onboard_api.dependencies import Responder
from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/messages", response_model=AssistantResponse)
def post_message(request: AssistantRequest, responder: Responder) -> AssistantResponse:
    # The responder comes from dependencies.get_assistant_responder. The
    # assistant owner replaces that dependency; this router stays unchanged.
    return responder(request)
