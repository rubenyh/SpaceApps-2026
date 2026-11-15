"""FastAPI dependencies of the wellbeing module.

Kept separate from onboard_api.dependencies on purpose (other teams own that
file). Tests override get_wellbeing_settings and get_wellbeing_clock.
"""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status

from onboard_api.wellbeing.database import (
    OnboardDatabaseUnavailable,
    connect_onboard_readonly,
    connect_wellbeing,
)
from onboard_api.wellbeing.onboard_reader import OnboardReader
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.settings import WellbeingSettings, get_wellbeing_settings

Clock = Callable[[], datetime]


def get_wellbeing_clock() -> Clock:
    return lambda: datetime.now(UTC)


SettingsDep = Annotated[WellbeingSettings, Depends(get_wellbeing_settings)]
ClockDep = Annotated[Clock, Depends(get_wellbeing_clock)]


def get_wellbeing_repository(settings: SettingsDep) -> Iterator[WellbeingRepository]:
    conn = connect_wellbeing(settings.db_path)
    try:
        yield WellbeingRepository(conn)
    finally:
        conn.close()


def get_onboard_reader(settings: SettingsDep) -> Iterator[OnboardReader]:
    try:
        conn: sqlite3.Connection = connect_onboard_readonly(settings.onboard_db_path)
    except OnboardDatabaseUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Onboard database unavailable: {exc}",
        ) from exc
    try:
        yield OnboardReader(conn)
    finally:
        conn.close()


RepoDep = Annotated[WellbeingRepository, Depends(get_wellbeing_repository)]
ReaderDep = Annotated[OnboardReader, Depends(get_onboard_reader)]
