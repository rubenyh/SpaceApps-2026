"""Shared FastAPI dependencies.

Tests override get_clock and get_assistant_deps (fake LLM, retriever,
readings and events) through app.dependency_overrides. Settings come from create_app(settings=...).
"""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from onboard_api.assistant.graph import build_assistant_graph, respond
from onboard_api.assistant.state import AssistantDeps
from onboard_api.config import Settings
from onboard_api.repositories.astronauts import AstronautRepository
from onboard_api.repositories.database import connect
from onboard_api.repositories.readings import ReadingRepository
from onboard_api.repositories.sensors import SensorConfigRepository
from onboard_api.services.assistant import AssistantResponder

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock() -> Clock:
    return utc_now


def get_connection(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[sqlite3.Connection]:
    """One SQLite connection per request, closed when the request ends."""
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


Connection = Annotated[sqlite3.Connection, Depends(get_connection)]


def get_astronaut_repository(conn: Connection) -> AstronautRepository:
    return AstronautRepository(conn)


def get_sensor_config_repository(conn: Connection) -> SensorConfigRepository:
    return SensorConfigRepository(conn)


def get_reading_repository(conn: Connection) -> ReadingRepository:
    return ReadingRepository(conn)


def get_assistant_deps(request: Request) -> AssistantDeps:
    """Shared integration clients built once in the lifespan."""
    return request.app.state.assistant_deps


def get_assistant_responder(
    deps: Annotated[AssistantDeps, Depends(get_assistant_deps)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AssistantResponder:
    graph = build_assistant_graph(deps)  # cached per deps object
    return lambda request: respond(graph, request, clock())


ClockDep = Annotated[Clock, Depends(get_clock)]
AstronautRepo = Annotated[AstronautRepository, Depends(get_astronaut_repository)]
SensorConfigRepo = Annotated[SensorConfigRepository, Depends(get_sensor_config_repository)]
ReadingRepo = Annotated[ReadingRepository, Depends(get_reading_repository)]
Responder = Annotated[AssistantResponder, Depends(get_assistant_responder)]
