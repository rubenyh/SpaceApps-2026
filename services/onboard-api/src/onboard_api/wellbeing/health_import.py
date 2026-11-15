"""Stream an Apple Health export (export.zip or export.xml) into wellbeing signals.

Reads HRV (SDNN), resting heart rate and sleep. export.xml can be hundreds of
MB, so it is parsed with iterparse and the tree is cleared after every Record:
memory stays flat. Nothing is sent from here; callers POST the signals.
"""

import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, tzinfo
from pathlib import Path
from typing import IO

from onboard_api.wellbeing.schemas import SignalCreate

HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
RESTING_HR = "HKQuantityTypeIdentifierRestingHeartRate"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
# Asleep stages. InBed and Awake are not sleep. "Asleep" is the pre-iOS 16 value.
ASLEEP = {
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
}
# Health unit -> (signal kind, API unit).
QUANTITIES = {HRV: ("hrv_sdnn", "ms", "ms"), RESTING_HR: ("resting_heart_rate", "count/min", "bpm")}
DEFAULT_SOURCE = "apple_watch_export"


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")


@contextmanager
def open_export(path: Path) -> Iterator[IO[bytes]]:
    """Binary stream of export.xml, from the zip (without extracting) or the file."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if Path(n).name == "export.xml"]
            if not names:
                raise ValueError(f"{path} has no export.xml")
            with archive.open(names[0]) as stream:
                yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def _merged_hours(intervals: list[tuple[datetime, datetime]]) -> float:
    """Total hours covered, counting overlaps once (Watch and iPhone overlap)."""
    total = 0.0
    current_start, current_end = None, None
    for start, end in sorted(intervals):
        if current_end is None or start > current_end:
            if current_end is not None:
                total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        total += (current_end - current_start).total_seconds()
    return total / 3600


def iter_signals(
    stream: IO[bytes],
    astronaut_id: str,
    since: date | None = None,
    source: str = DEFAULT_SOURCE,
    tz: tzinfo = UTC,
) -> Iterator[SignalCreate]:
    """HRV and resting HR as they stream by; one sleep_hours per wake-up day at the end.

    Days (the `since` filter and a night's wake-up day) are mission days in `tz`,
    the API's WELLBEING_MISSION_TZ.
    """
    sleep: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
    root = None
    for event, elem in ET.iterparse(stream, events=("start", "end")):
        if root is None:
            root = elem
        if event != "end" or elem.tag != "Record":
            continue
        kind = elem.get("type")
        if kind in QUANTITIES:
            signal_kind, health_unit, unit = QUANTITIES[kind]
            start = _parse_date(elem.get("startDate", ""))
            if elem.get("unit") == health_unit and (
                since is None or start.astimezone(tz).date() >= since
            ):
                yield SignalCreate(
                    astronaut_id=astronaut_id,
                    kind=signal_kind,
                    value=float(elem.get("value", "nan")),
                    unit=unit,
                    recorded_at=start,
                    quality="good",
                    source=source,
                )
        elif kind == SLEEP and elem.get("value") in ASLEEP:
            start = _parse_date(elem.get("startDate", ""))
            end = _parse_date(elem.get("endDate", ""))
            sleep[end.astimezone(tz).date()].append((start, end))
        root.clear()  # drop processed Records so memory stays flat

    for wake_day, intervals in sorted(sleep.items()):
        if since is not None and wake_day < since:
            continue
        yield SignalCreate(
            astronaut_id=astronaut_id,
            kind="sleep_hours",
            value=round(_merged_hours(intervals), 2),
            unit="h",
            recorded_at=max(end for _, end in intervals),
            quality="good",
            source=source,
        )
