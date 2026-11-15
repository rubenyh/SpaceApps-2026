"""Shared helpers for wellbeing tests (not a conftest, to avoid clashing with
tests/conftest.py, which other test modules import by name)."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onboard_api.repositories.database import connect, init_db, to_db_timestamp
from onboard_api.wellbeing.dependencies import get_wellbeing_clock
from onboard_api.wellbeing.engine import DailyInputs
from onboard_api.wellbeing.router import router
from onboard_api.wellbeing.settings import WellbeingSettings, get_wellbeing_settings

NOW = datetime(2026, 11, 14, 18, 0, 0, tzinfo=UTC)
TODAY = NOW.date()


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make_onboard_db(path: Path, astronauts: dict[str, str]) -> Path:
    init_db(path, now=NOW)
    conn = connect(path)
    try:
        conn.executemany(
            "INSERT INTO astronauts (id, display_name, created_at) VALUES (?, ?, ?)",
            [(aid, name, to_db_timestamp(NOW)) for aid, name in astronauts.items()],
        )
    finally:
        conn.close()
    return path


def insert_heart_rates(path: Path, astronaut_id: str, values: list[tuple[datetime, float, str]]) -> None:
    conn = connect(path)
    try:
        conn.executemany(
            "INSERT INTO readings (astronaut_id, kind, value, unit, recorded_at,"
            " received_at, quality, source) VALUES (?, 'heart_rate', ?, 'bpm', ?, ?, ?, 'test')",
            [
                (astronaut_id, value, to_db_timestamp(at), to_db_timestamp(NOW), quality)
                for at, value, quality in values
            ],
        )
    finally:
        conn.close()


@pytest.fixture
def wb_settings(tmp_path: Path) -> WellbeingSettings:
    onboard = make_onboard_db(
        tmp_path / "onboard.db", {"ast-01": "X", "ast-02": "Y", "ast-03": "Z"}
    )
    return WellbeingSettings(db_path=tmp_path / "wb" / "wellbeing.db", onboard_db_path=onboard)


@pytest.fixture
def wb_clock() -> Clock:
    return Clock(NOW)


@pytest.fixture
def wb_client(wb_settings: WellbeingSettings, wb_clock: Clock) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_wellbeing_settings] = lambda: wb_settings
    app.dependency_overrides[get_wellbeing_clock] = lambda: wb_clock
    with TestClient(app) as client:
        yield client


def checkin_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "sleep_hours": 7.5,
        "sleep_quality": 3,
        "energy": 3,
        "mood": 3,
        "interest": 3,
        "stress": 1,
        "crew_connection": 3,
    }
    body.update(overrides)
    return body


def series_inputs(
    series: dict[str, Callable[[int], float | None]], days: int, end: date = TODAY
) -> DailyInputs:
    """DailyInputs from per-component functions of the day index (0 = first)."""
    inputs = DailyInputs()
    start = end - timedelta(days=days - 1)
    for name, fn in series.items():
        for i in range(days):
            value = fn(i)
            if value is not None:
                inputs.values[name][start + timedelta(days=i)] = value
    for i in range(days):
        day = start + timedelta(days=i)
        if any(day in s for k, s in inputs.values.items() if k.startswith("checkin.")):
            inputs.checkin_days.add(day)
    return inputs
