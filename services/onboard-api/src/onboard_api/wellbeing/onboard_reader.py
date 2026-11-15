"""Read-only access to the onboard service's data through its repositories.

The connection is opened with mode=ro. Physical readings are never written
here: use POST /readings for that.
"""

import sqlite3

from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.schemas.astronauts import Astronaut
from onboard_api.schemas.readings import Reading


class OnboardReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._astronauts = AstronautRepository(conn)
        self._readings = ReadingRepository(conn)

    def list_astronauts(self) -> list[Astronaut]:
        return self._astronauts.list_all()

    def get_astronaut(self, astronaut_id: str) -> Astronaut | None:
        return self._astronauts.get(astronaut_id)

    def heart_rate_readings(self, astronaut_id: str) -> list[Reading]:
        return self._readings.numeric_series(astronaut_id, "heart_rate", "bpm")
