from fastapi import APIRouter, HTTPException, status

from onboard_api.dependencies import AstronautRepo, ClockDep, ReadingRepo, SensorConfigRepo
from onboard_api.schemas.common import ErrorResponse
from onboard_api.schemas.status import AstronautStatus
from onboard_api.services.astronauts import AstronautNotFoundError
from onboard_api.services.status import get_astronaut_status

router = APIRouter(tags=["status"])


@router.get(
    "/astronauts/{astronaut_id}/status",
    response_model=AstronautStatus,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def astronaut_status(
    astronaut_id: str,
    astronauts: AstronautRepo,
    sensors: SensorConfigRepo,
    readings: ReadingRepo,
    clock: ClockDep,
) -> AstronautStatus:
    try:
        return get_astronaut_status(astronauts, sensors, readings, astronaut_id, now=clock())
    except AstronautNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
