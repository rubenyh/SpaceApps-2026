from fastapi import APIRouter, HTTPException, Response, status

from onboard_api.dependencies import AstronautRepo, ClockDep, IncidentRepo
from onboard_api.schemas.common import ErrorResponse
from onboard_api.schemas.incidents import AcknowledgmentCreate, Incident, IncidentStatus

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


@router.post(
    "/{incident_id}/acknowledgments",
    response_model=Incident,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"model": Incident, "description": "Already acknowledged by this person"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
def acknowledge_incident(
    incident_id: str,
    data: AcknowledgmentCreate,
    response: Response,
    incidents: IncidentRepo,
    astronauts: AstronautRepo,
    clock: ClockDep,
) -> Incident:
    """Crew acknowledgment, stored onboard only. Ground delivery is tracked separately."""
    if incidents.get(incident_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"incident {incident_id} not found")
    if not astronauts.exists(data.acknowledged_by):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"astronaut {data.acknowledged_by} not found",
        )
    if not incidents.acknowledge(incident_id, data.acknowledged_by, clock()):
        response.status_code = status.HTTP_200_OK
    return incidents.get(incident_id)
