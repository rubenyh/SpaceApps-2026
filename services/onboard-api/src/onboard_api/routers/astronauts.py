from fastapi import APIRouter, HTTPException, status

from onboard_api.dependencies import AstronautRepo, ClockDep
from onboard_api.schemas.astronauts import Astronaut, AstronautCreate
from onboard_api.schemas.common import ErrorResponse
from onboard_api.services.astronauts import AstronautAlreadyExistsError, create_astronaut

router = APIRouter(prefix="/astronauts", tags=["astronauts"])


@router.get("", response_model=list[Astronaut])
def list_astronauts(repo: AstronautRepo) -> list[Astronaut]:
    return repo.list_all()


@router.post(
    "",
    response_model=Astronaut,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
def post_astronaut(data: AstronautCreate, repo: AstronautRepo, clock: ClockDep) -> Astronaut:
    try:
        return create_astronaut(repo, data, now=clock())
    except AstronautAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
