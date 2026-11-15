"""Glue between storage, the read-only onboard data and the fusion engine."""

import uuid
from datetime import date, datetime, time, timedelta

from onboard_api.wellbeing import engine
from onboard_api.wellbeing.onboard_reader import OnboardReader
from onboard_api.wellbeing.repository import WellbeingRepository
from onboard_api.wellbeing.schemas import (
    SOURCES,
    CheckinUpsert,
    Checkin,
    ComponentParameter,
    ComponentState,
    CoPresence,
    CoPresenceCreate,
    CrewMemberSummary,
    CrewWellbeing,
    GroundPackage,
    GroundPackageContent,
    GroundPackageCreate,
    IndicatorState,
    Signal,
    SignalCreate,
    TimelineDay,
    VisionSession,
    VisionSessionCreate,
    WellbeingAssessment,
    WellbeingParameters,
    WellbeingTimeline,
    is_unknown_person,
)
from onboard_api.wellbeing.settings import BASIS, WellbeingSettings


class AstronautNotFoundError(Exception):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Astronaut '{astronaut_id}' not found")


class FutureDayError(Exception):
    def __init__(self, day: date) -> None:
        super().__init__(f"Day {day.isoformat()} is in the future")


def _ensure_astronauts(reader: OnboardReader, *astronaut_ids: str) -> None:
    for astronaut_id in astronaut_ids:
        if not is_unknown_person(astronaut_id) and reader.get_astronaut(astronaut_id) is None:
            raise AstronautNotFoundError(astronaut_id)


def get_parameters(settings: WellbeingSettings) -> WellbeingParameters:
    return WellbeingParameters(
        provisional=True,
        basis=BASIS,
        mission_tz=settings.mission_tz,
        z_threshold=settings.z_threshold,
        sustain_days=settings.sustain_days,
        baseline_days=settings.baseline_days,
        baseline_min_days=settings.baseline_min_days,
        adaptation_days=settings.adaptation_days,
        stale_after_days=settings.stale_after_days,
        trend_window_days=settings.trend_window_days,
        trend_min_delta=settings.trend_min_delta,
        z_cap=settings.z_cap,
        components=[
            ComponentParameter(
                component=c.component,
                source=c.source,
                indicator=c.indicator,
                adverse_direction=c.adverse,
                scale_floor=c.scale_floor,
                unit=c.unit,
            )
            for c in engine.COMPONENTS
        ],
    )


# --- Inputs ---


def upsert_checkin(
    repo: WellbeingRepository,
    reader: OnboardReader,
    astronaut_id: str,
    day: date,
    data: CheckinUpsert,
    settings: WellbeingSettings,
    now: datetime,
) -> Checkin:
    _ensure_astronauts(reader, astronaut_id)
    if day > settings.day_of(now):
        raise FutureDayError(day)
    return repo.upsert_checkin(astronaut_id, day, data, submitted_at=now)


def list_checkins(
    repo: WellbeingRepository,
    reader: OnboardReader,
    astronaut_id: str,
    since: date | None,
    until: date | None,
) -> list[Checkin]:
    _ensure_astronauts(reader, astronaut_id)
    return repo.list_checkins(astronaut_id, since, until)


def record_signal(
    repo: WellbeingRepository, reader: OnboardReader, data: SignalCreate, now: datetime
) -> Signal:
    _ensure_astronauts(reader, data.astronaut_id)
    return repo.create_signal(data, received_at=now)


def record_vision_session(
    repo: WellbeingRepository, reader: OnboardReader, data: VisionSessionCreate, now: datetime
) -> VisionSession:
    _ensure_astronauts(reader, data.astronaut_id)
    return repo.create_vision_session(data, received_at=now)


def record_co_presence(
    repo: WellbeingRepository, reader: OnboardReader, data: CoPresenceCreate, now: datetime
) -> CoPresence:
    _ensure_astronauts(reader, *(o.astronaut_id for o in data.occupants))
    return repo.create_co_presence(data, received_at=now)


# --- Outputs ---


def load_inputs(
    repo: WellbeingRepository,
    reader: OnboardReader,
    astronaut_id: str,
    settings: WellbeingSettings,
) -> engine.DailyInputs:
    return engine.build_daily_inputs(
        astronaut_id,
        checkins=repo.list_checkins(astronaut_id),
        signals=repo.list_signals(astronaut_id),
        vision=repo.list_vision_sessions(astronaut_id),
        co_presence=repo.list_co_presence(astronaut_id),
        heart_rates=reader.heart_rate_readings(astronaut_id),
        settings=settings,
    )


def _component_state(ce: engine.ComponentEval, inputs: engine.DailyInputs) -> ComponentState:
    return ComponentState(
        component=ce.definition.component,
        source=ce.definition.source,
        latest_value=ce.latest_value,
        unit=ce.definition.unit,
        z=_round(ce.latest_z),
        baseline_median=_round(ce.baseline_median),
        baseline_scale=_round(ce.baseline_scale),
        baseline_days=len(ce.baseline_days),
        baseline_from=ce.baseline_days[0] if ce.baseline_days else None,
        baseline_to=ce.baseline_days[-1] if ce.baseline_days else None,
        baseline_ready=ce.ready,
        latest_day=ce.latest_day,
        latest_origin=(
            inputs.origin(ce.latest_day, [ce.definition.component]) if ce.latest_day else None
        ),
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def get_assessment(
    repo: WellbeingRepository,
    reader: OnboardReader,
    astronaut_id: str,
    settings: WellbeingSettings,
    now: datetime,
) -> WellbeingAssessment:
    _ensure_astronauts(reader, astronaut_id)
    inputs = load_inputs(repo, reader, astronaut_id, settings)
    today = settings.day_of(now)
    ev = engine.evaluate(inputs, today, settings)
    counts = engine.origin_counts(inputs, today)
    return WellbeingAssessment(
        astronaut_id=astronaut_id,
        generated_at=now,
        level=ev.level,
        confidence=ev.confidence,
        trend=ev.trend,
        onset_date=ev.onset_date,
        sustained_days=ev.sustained_days,
        discrepancy=ev.discrepancy,
        sustained_sources=ev.sustained_sources,
        latest_day=ev.latest_day,
        indicators=[
            IndicatorState(
                kind=ind.kind,
                status=ind.status,
                z=_round(ind.z),
                deviant_since=ind.run.start if ind.run else None,
                sources=ind.sources,
                latest_day=ind.latest_day,
                latest_origin=(
                    inputs.origin(ind.latest_day, [ce.definition.component for ce in ind.components])
                    if ind.latest_day
                    else None
                ),
                components=[_component_state(ce, inputs) for ce in ind.components],
            )
            for ind in ev.indicators
        ],
        support_notes=engine.support_notes(ev, settings),
        data_notices=engine.data_notices(inputs, today),
        latest_origin=inputs.origin(ev.latest_day) if ev.latest_day else None,
        live_days=counts["live"],
        simulated_days=counts["simulated"],
        mixed_days=counts["mixed"],
    )


def get_timeline(
    repo: WellbeingRepository,
    reader: OnboardReader,
    astronaut_id: str,
    settings: WellbeingSettings,
    now: datetime,
    days: int,
) -> WellbeingTimeline:
    _ensure_astronauts(reader, astronaut_id)
    inputs = load_inputs(repo, reader, astronaut_id, settings)
    today = settings.day_of(now)
    data_days = inputs.data_days
    timeline: list[TimelineDay] = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        # Each day is judged with the data available up to that day only.
        ev = engine.evaluate(inputs, day, settings)
        timeline.append(
            TimelineDay(
                day=day,
                level=ev.level,
                has_data=day in data_days,
                has_checkin=day in inputs.checkin_days,
                origin=inputs.origin(day),
                indicators={ind.kind: _round(ind.z_by_day.get(day)) for ind in ev.indicators},
                sources={s: _round(ev.source_z_by_day[s].get(day)) for s in SOURCES},
            )
        )
    current = engine.evaluate(inputs, today, settings)
    return WellbeingTimeline(
        astronaut_id=astronaut_id,
        generated_at=now,
        onset_date=current.onset_date,
        z_threshold=settings.z_threshold,
        days=timeline,
    )


def get_crew(
    repo: WellbeingRepository,
    reader: OnboardReader,
    settings: WellbeingSettings,
    now: datetime,
) -> CrewWellbeing:
    today = settings.day_of(now)
    members: list[CrewMemberSummary] = []
    for astronaut in reader.list_astronauts():
        inputs = load_inputs(repo, reader, astronaut.id, settings)
        ev = engine.evaluate(inputs, today, settings)
        members.append(
            CrewMemberSummary(
                astronaut_id=astronaut.id,
                display_name=astronaut.display_name,
                level=ev.level,
                trend=ev.trend,
                latest_origin=inputs.origin(ev.latest_day) if ev.latest_day else None,
            )
        )
    return CrewWellbeing(generated_at=now, members=members)


# --- Ground psychologist packages ---


class PackageNotFoundError(Exception):
    def __init__(self, package_id: str) -> None:
        super().__init__(f"Ground package '{package_id}' not found")


class PackageStateError(Exception):
    pass


def create_ground_package(
    repo: WellbeingRepository,
    reader: OnboardReader,
    data: GroundPackageCreate,
    settings: WellbeingSettings,
    now: datetime,
) -> GroundPackage:
    """Queue a package on board. Consent is validated by GroundPackageCreate."""
    if reader.get_astronaut(data.astronaut_id) is None:
        raise AstronautNotFoundError(data.astronaut_id)
    if data.period_to > settings.day_of(now):
        raise FutureDayError(data.period_to)
    return repo.create_ground_package(str(uuid.uuid4()), data, now)


def list_ground_packages(
    repo: WellbeingRepository, reader: OnboardReader, astronaut_id: str
) -> list[GroundPackage]:
    _ensure_astronauts(reader, astronaut_id)
    return repo.list_ground_packages(astronaut_id)


def _get_package(repo: WellbeingRepository, package_id: str) -> GroundPackage:
    package = repo.get_ground_package(package_id)
    if package is None:
        raise PackageNotFoundError(package_id)
    return package


def get_ground_package_content(
    repo: WellbeingRepository,
    reader: OnboardReader,
    settings: WellbeingSettings,
    package_id: str,
    now: datetime,
) -> GroundPackageContent:
    """Exactly what would be sent: the data as of the end of the period."""
    package = _get_package(repo, package_id)
    if package.status == "withdrawn":
        raise PackageStateError("Consent for this package was withdrawn")
    aid, include = package.astronaut_id, package.include
    as_of = min(now, datetime.combine(package.period_to, time.max, tzinfo=settings.tz))
    days = (package.period_to - package.period_from).days + 1
    checkins = None
    if "checkins" in include:
        checkins = repo.list_checkins(aid, package.period_from, package.period_to)
        if "comments" not in include:
            checkins = [c.model_copy(update={"comment": None}) for c in checkins]
    return GroundPackageContent(
        package=package,
        assessment=get_assessment(repo, reader, aid, settings, as_of)
        if "assessment" in include
        else None,
        timeline=get_timeline(repo, reader, aid, settings, as_of, days)
        if "timeline" in include
        else None,
        checkins=checkins,
    )


def withdraw_ground_package(
    repo: WellbeingRepository, package_id: str, now: datetime
) -> GroundPackage:
    package = _get_package(repo, package_id)
    if package.status == "sent":
        raise PackageStateError("Package already sent; it can no longer be withdrawn")
    if package.status == "queued":
        repo.set_ground_package_status(package_id, "withdrawn", now)
    return _get_package(repo, package_id)
