import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from onboard_api.config import Settings
from onboard_api.dependencies import ClockDep, IncidentRecorderDep, Responder, get_settings
from onboard_api.knowledge import active_version
from onboard_api.schemas.assistant import AssistantRequest, AssistantResponse, IncidentRef

router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


@router.post("/messages", response_model=AssistantResponse)
def post_message(
    request: AssistantRequest,
    responder: Responder,
    record_incident: IncidentRecorderDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantResponse:
    # The responder comes from dependencies.get_assistant_responder. The
    # assistant owner replaces that dependency; this router stays unchanged.
    response = responder(request)
    if response.report is not None:
        version = active_version(settings.knowledge_dir)
        response.report.knowledge_version = version
        response.report.text += (
            f"\n\nApproved knowledge bundle active: {version.candidate_id} (digest {version.digest})"
            if version else "\n\nApproved knowledge bundle active: none"
        )
    if response.urgency == "immediate":
        # A storage failure never hides the action: it is reported next to it.
        try:
            incident_id = record_incident(
                response, request.astronaut_id, request.reported_by, clock(), request.source
            )
            response.incident = IncidentRef(id=incident_id, recorded=True)
        except Exception as exc:
            logger.exception("incident not recorded")
            response.incident = IncidentRef(
                recorded=False, error=f"onboard database error ({type(exc).__name__}: {exc})"
            )
    return response
