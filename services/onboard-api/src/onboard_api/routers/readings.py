from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime

from onboard_api.dependencies import AstronautRepo, ClockDep, ReadingRepo, SensorConfigRepo
from onboard_api.schemas.common import ErrorResponse
from onboard_api.schemas.readings import Reading, ReadingCreate
from onboard_api.schemas.sensors import SensorKind
from onboard_api.services.astronauts import AstronautNotFoundError
from onboard_api.services.readings import UnitMismatchError, list_readings, record_reading

router = APIRouter(prefix="/readings", tags=["readings"])

_NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


@router.post(
    "",
    response_model=Reading,
    status_code=status.HTTP_201_CREATED,
    responses=_NOT_FOUND,
)
def post_reading(
    data: ReadingCreate,
    astronauts: AstronautRepo,
    sensors: SensorConfigRepo,
    readings: ReadingRepo,
    clock: ClockDep,
) -> Reading:
    try:
        return record_reading(astronauts, sensors, readings, data, now=clock())
    except AstronautNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnitMismatchError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("", response_model=list[Reading], responses=_NOT_FOUND)
def get_readings(
    astronauts: AstronautRepo,
    readings: ReadingRepo,
    astronaut_id: str,
    kind: SensorKind | None = None,
    since: Annotated[AwareDatetime | None, Query(description="Inclusive lower bound")] = None,
    until: Annotated[AwareDatetime | None, Query(description="Inclusive upper bound")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[Reading]:
    """Readings of one astronaut, newest first by recorded_at."""
    try:
        return list_readings(astronauts, readings, astronaut_id, kind, since, until, limit)
    except AstronautNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
