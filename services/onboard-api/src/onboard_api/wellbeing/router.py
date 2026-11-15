"""Wellbeing routes. Contract: docs/wellbeing-contract.md.

Register in main.py with `app.include_router(wellbeing_router)` (pending,
coordinated with the onboard owner).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from onboard_api.schemas.common import ErrorResponse
from onboard_api.wellbeing import service
from onboard_api.wellbeing.checkin_form import CHECKIN_FORM
from onboard_api.wellbeing.dependencies import ClockDep, ReaderDep, RepoDep, SettingsDep
from onboard_api.wellbeing.schemas import (
    Checkin,
    CheckinForm,
    CheckinUpsert,
    CoPresence,
    CoPresenceCreate,
    CrewWellbeing,
    GroundPackage,
    GroundPackageContent,
    GroundPackageCreate,
    Signal,
    SignalCreate,
    VisionSession,
    VisionSessionCreate,
    WellbeingAssessment,
    WellbeingParameters,
    WellbeingTimeline,
)

router = APIRouter(tags=["wellbeing"])

_NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


def _not_found(exc: service.AstronautNotFoundError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/wellbeing/parameters", response_model=WellbeingParameters)
def parameters(settings: SettingsDep) -> WellbeingParameters:
    return service.get_parameters(settings)


@router.get("/wellbeing/checkin-form", response_model=CheckinForm)
def checkin_form() -> CheckinForm:
    return CHECKIN_FORM


@router.put(
    "/astronauts/{astronaut_id}/wellbeing/checkins/{day}",
    response_model=Checkin,
    responses=_NOT_FOUND,
)
def put_checkin(
    astronaut_id: str,
    day: date,
    data: CheckinUpsert,
    repo: RepoDep,
    reader: ReaderDep,
    clock: ClockDep,
) -> Checkin:
    try:
        return service.upsert_checkin(repo, reader, astronaut_id, day, data, now=clock())
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc
    except service.FutureDayError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get(
    "/astronauts/{astronaut_id}/wellbeing/checkins",
    response_model=list[Checkin],
    responses=_NOT_FOUND,
)
def get_checkins(
    astronaut_id: str,
    repo: RepoDep,
    reader: ReaderDep,
    since: Annotated[date | None, Query(description="Inclusive")] = None,
    until: Annotated[date | None, Query(description="Inclusive")] = None,
) -> list[Checkin]:
    """Personal view only: includes the private comment."""
    try:
        return service.list_checkins(repo, reader, astronaut_id, since, until)
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/wellbeing/signals",
    response_model=Signal,
    status_code=status.HTTP_201_CREATED,
    responses=_NOT_FOUND,
)
def post_signal(
    data: SignalCreate, repo: RepoDep, reader: ReaderDep, clock: ClockDep
) -> Signal:
    try:
        return service.record_signal(repo, reader, data, now=clock())
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/wellbeing/vision-sessions",
    response_model=VisionSession,
    status_code=status.HTTP_201_CREATED,
    responses=_NOT_FOUND,
)
def post_vision_session(
    data: VisionSessionCreate, repo: RepoDep, reader: ReaderDep, clock: ClockDep
) -> VisionSession:
    try:
        return service.record_vision_session(repo, reader, data, now=clock())
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/wellbeing/co-presence",
    response_model=CoPresence,
    status_code=status.HTTP_201_CREATED,
    responses=_NOT_FOUND,
)
def post_co_presence(
    data: CoPresenceCreate, repo: RepoDep, reader: ReaderDep, clock: ClockDep
) -> CoPresence:
    try:
        return service.record_co_presence(repo, reader, data, now=clock())
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/wellbeing/crew", response_model=CrewWellbeing)
def crew(
    repo: RepoDep, reader: ReaderDep, settings: SettingsDep, clock: ClockDep
) -> CrewWellbeing:
    """Crew view: level and trend only, no detail."""
    return service.get_crew(repo, reader, settings, now=clock())


@router.get(
    "/astronauts/{astronaut_id}/wellbeing",
    response_model=WellbeingAssessment,
    responses=_NOT_FOUND,
)
def assessment(
    astronaut_id: str,
    repo: RepoDep,
    reader: ReaderDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> WellbeingAssessment:
    try:
        return service.get_assessment(repo, reader, astronaut_id, settings, now=clock())
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/astronauts/{astronaut_id}/wellbeing/timeline",
    response_model=WellbeingTimeline,
    responses=_NOT_FOUND,
)
def timeline(
    astronaut_id: str,
    repo: RepoDep,
    reader: ReaderDep,
    settings: SettingsDep,
    clock: ClockDep,
    days: Annotated[int, Query(ge=1, le=120)] = 30,
) -> WellbeingTimeline:
    try:
        return service.get_timeline(
            repo, reader, astronaut_id, settings, now=clock(), days=days
        )
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


# --- Ground psychologist packages: manual, explicit consent, queued on board ---

_PACKAGE_ERRORS = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
}


@router.post(
    "/wellbeing/ground-packages",
    response_model=GroundPackage,
    status_code=status.HTTP_201_CREATED,
    responses=_NOT_FOUND,
)
def post_ground_package(
    data: GroundPackageCreate, repo: RepoDep, reader: ReaderDep, clock: ClockDep
) -> GroundPackage:
    try:
        return service.create_ground_package(repo, reader, data, now=clock())
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc
    except service.FutureDayError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get(
    "/wellbeing/ground-packages", response_model=list[GroundPackage], responses=_NOT_FOUND
)
def get_ground_packages(
    astronaut_id: str, repo: RepoDep, reader: ReaderDep
) -> list[GroundPackage]:
    try:
        return service.list_ground_packages(repo, reader, astronaut_id)
    except service.AstronautNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/wellbeing/ground-packages/{package_id}/content",
    response_model=GroundPackageContent,
    responses=_PACKAGE_ERRORS,
)
def get_ground_package_content(
    package_id: str, repo: RepoDep, reader: ReaderDep, settings: SettingsDep, clock: ClockDep
) -> GroundPackageContent:
    try:
        return service.get_ground_package_content(
            repo, reader, settings, package_id, now=clock()
        )
    except service.PackageNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.PackageStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/wellbeing/ground-packages/{package_id}/withdraw",
    response_model=GroundPackage,
    responses=_PACKAGE_ERRORS,
)
def withdraw_ground_package(package_id: str, repo: RepoDep, clock: ClockDep) -> GroundPackage:
    try:
        return service.withdraw_ground_package(repo, package_id, now=clock())
    except service.PackageNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.PackageStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
