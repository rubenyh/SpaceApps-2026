from datetime import datetime

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.schemas.astronauts import Astronaut, AstronautCreate, AstronautUpdate


class AstronautNotFoundError(Exception):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Astronaut '{astronaut_id}' not found")
        self.astronaut_id = astronaut_id


class AstronautAlreadyExistsError(Exception):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Astronaut '{astronaut_id}' already exists")
        self.astronaut_id = astronaut_id


def ensure_astronaut_exists(repo: AstronautRepository, astronaut_id: str) -> None:
    if not repo.exists(astronaut_id):
        raise AstronautNotFoundError(astronaut_id)


def create_astronaut(
    repo: AstronautRepository, data: AstronautCreate, now: datetime
) -> Astronaut:
    astronaut = repo.create(data, created_at=now)
    if astronaut is None:
        raise AstronautAlreadyExistsError(data.id)
    return astronaut


def rename_astronaut(
    repo: AstronautRepository, astronaut_id: str, data: AstronautUpdate
) -> Astronaut:
    astronaut = repo.rename(astronaut_id, data.display_name)
    if astronaut is None:
        raise AstronautNotFoundError(astronaut_id)
    return astronaut
