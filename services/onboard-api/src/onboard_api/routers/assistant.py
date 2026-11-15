import logging

from fastapi import APIRouter

from onboard_api.dependencies import ClockDep, IncidentRecorderDep, Responder
from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse, IncidentRef

router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


@router.post("/messages", response_model=AssistantResponse)
def post_message(
    request: AssistantRequest,
    responder: Responder,
    record_incident: IncidentRecorderDep,
    clock: ClockDep,
) -> AssistantResponse:
    # The responder comes from dependencies.get_assistant_responder. The
    # assistant owner replaces that dependency; this router stays unchanged.
    response = responder(request)
    if response.urgency == "immediate":
        # A storage failure never hides the action: it is reported next to it.
        try:
            incident_id = record_incident(
                response, request.astronaut_id, request.reported_by, clock()
            )
            response.incident = IncidentRef(id=incident_id, recorded=True)
        except Exception as exc:
            logger.exception("incident not recorded")
            response.incident = IncidentRef(
                recorded=False, error=f"onboard database error ({type(exc).__name__}: {exc})"
            )
    return response
