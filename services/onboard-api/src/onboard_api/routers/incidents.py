from fastapi import APIRouter, HTTPException, status

from onboard_api.dependencies import IncidentRepo
from onboard_api.schemas.common import ErrorResponse
from onboard_api.schemas.incidents import Incident, IncidentStatus

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[Incident])
def list_incidents(incidents: IncidentRepo, status: IncidentStatus | None = None) -> list[Incident]:
    """Open incidents first, then newest began_at first."""
    return incidents.list_all(status)


@router.get(
    "/{incident_id}",
    response_model=Incident,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def get_incident(incident_id: str, incidents: IncidentRepo) -> Incident:
    incident = incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"incident {incident_id} not found")
    return incident
