from fastapi import APIRouter, HTTPException, status

from onboard_api.dependencies import AstronautRepo, ClockDep
from onboard_api.schemas.astronauts import Astronaut, AstronautCreate, AstronautUpdate
from onboard_api.schemas.common import ErrorResponse
from onboard_api.services.astronauts import (
    AstronautAlreadyExistsError,
    AstronautNotFoundError,
    create_astronaut,
    rename_astronaut,
)

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


@router.patch(
    "/{astronaut_id}",
    response_model=Astronaut,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def patch_astronaut(astronaut_id: str, data: AstronautUpdate, repo: AstronautRepo) -> Astronaut:
    """Rename an astronaut. Only `display_name` changes; ids are permanent."""
    try:
        return rename_astronaut(repo, astronaut_id, data)
    except AstronautNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
