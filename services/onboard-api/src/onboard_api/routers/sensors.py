from fastapi import APIRouter, HTTPException, status

from onboard_api.dependencies import ClockDep, SensorConfigRepo
from onboard_api.schemas.common import ErrorResponse
from onboard_api.schemas.sensors import SensorConfig, SensorConfigUpdate

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("", response_model=list[SensorConfig])
def list_sensors(repo: SensorConfigRepo) -> list[SensorConfig]:
    return repo.list_all()


@router.put(
    "/{kind}",
    response_model=SensorConfig,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def put_sensor(
    kind: str, data: SensorConfigUpdate, repo: SensorConfigRepo, clock: ClockDep
) -> SensorConfig:
    # kind is a plain string so an unknown kind is a 404, not a 422.
    config = repo.update(kind, data, updated_at=clock())
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Sensor kind '{kind}' not found")
    return config
