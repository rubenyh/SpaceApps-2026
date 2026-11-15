"""Fusion engine: personal baselines, adverse z-scores, sustained runs, levels.

Pure functions over in-memory data. Every threshold comes from
WellbeingSettings and is a PROVISIONAL design parameter, not a clinical one.
The method is described in docs/wellbeing-contract.md ("Cómo se calcula").
"""

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from onboard_api.schemas.readings import Reading
from onboard_api.wellbeing.schemas import (
    INDICATOR_KINDS,
    SOURCES,
    AdverseDirection,
    Checkin,
    CoPresence,
    Origin,
    Confidence,
    IndicatorKind,
    IndicatorStatus,
    Signal,
    SupportLevel,
    Trend,
    VisionSession,
    WellbeingSource,
    is_simulated_source,
)
from onboard_api.wellbeing.settings import WellbeingSettings

# 1.4826 * MAD estimates the standard deviation for normally distributed data.
_MAD_TO_SD = 1.4826


@dataclass(frozen=True)
class ComponentDef:
    component: str
    source: WellbeingSource
    indicator: IndicatorKind
    adverse: AdverseDirection
    # Minimum baseline scale, so a very stable baseline does not turn tiny
    # changes into large z-scores. PROVISIONAL.
    scale_floor: float
    unit: str


COMPONENTS: tuple[ComponentDef, ...] = (
    ComponentDef("checkin.sleep_hours", "checkin", "sleep", "low", 1.0, "h"),
    ComponentDef("checkin.sleep_quality", "checkin", "sleep", "low", 1.0, "0-4"),
    ComponentDef("signal.sleep_hours", "physiology", "sleep", "low", 0.5, "h"),
    ComponentDef("checkin.energy", "checkin", "fatigue", "low", 1.0, "0-4"),
    # Vision floors ~ day-to-day spread at rest (one real session, ~50 cm):
    # one extra yawn in a 90 s log is already +0.67/min.
    ComponentDef("vision.perclos", "vision", "fatigue", "high", 0.03, "ratio"),
    ComponentDef("vision.eye_openness_vs_neutral", "vision", "fatigue", "low", 0.05, "ratio"),
    ComponentDef("vision.yawns_per_min", "vision", "fatigue", "high", 0.5, "1/min"),
    ComponentDef("vision.nods_per_min", "vision", "fatigue", "high", 0.5, "1/min"),
    ComponentDef("checkin.stress", "checkin", "stress", "high", 1.0, "0-4"),
    ComponentDef("signal.hrv_sdnn", "physiology", "stress", "low", 5.0, "ms"),
    ComponentDef("signal.resting_heart_rate", "physiology", "stress", "high", 2.0, "bpm"),
    ComponentDef("onboard.heart_rate_low", "physiology", "stress", "high", 2.0, "bpm"),
    ComponentDef("vision.brow_lower_delta", "vision", "stress", "high", 0.03, "0-1"),
    # Peaks keep brief grimaces that the session mean dilutes.
    ComponentDef("vision.brow_lower_peak_1s", "vision", "stress", "high", 0.05, "0-1"),
    # lip_press_* is stored but not scored: talking peaks at 0.41-0.49 at rest,
    # above deliberate lip pressing (real logs, 2026-11-15). Re-add once vision
    # filters speech.
    ComponentDef("vision.speed", "vision", "activation", "both", 0.05, "shoulders/s"),
    ComponentDef("vision.stationary_ratio", "vision", "activation", "both", 0.05, "ratio"),
    ComponentDef("vision.fidget_index", "vision", "activation", "high", 0.05, "index"),
    ComponentDef("vision.torso_angle_dev", "vision", "activation", "high", 2.0, "deg"),
    ComponentDef("social.accompanied_minutes", "social", "social", "low", 10.0, "min"),
    ComponentDef("checkin.crew_connection", "checkin", "social", "low", 1.0, "0-4"),
    ComponentDef("checkin.mood", "checkin", "mood", "low", 1.0, "0-4"),
    ComponentDef("checkin.interest", "checkin", "mood", "low", 1.0, "0-4"),
)
COMPONENTS_BY_NAME = {c.component: c for c in COMPONENTS}

_CHECKIN_ITEMS = (
    "sleep_hours",
    "sleep_quality",
    "energy",
    "stress",
    "crew_connection",
    "mood",
    "interest",
)

SOURCE_LABELS: dict[WellbeingSource, str] = {
    "checkin": "checklist diario",
    "vision": "cámara",
    "physiology": "datos fisiológicos",
    "social": "interacción social",
}


# --- Daily inputs ---


def _origin(kinds: Iterable[str]) -> Origin | None:
    found = set(kinds)
    if not found:
        return None
    return "mixed" if len(found) > 1 else found.pop()  # type: ignore[return-value]


def _source_kind(source: str) -> str:
    return "simulated" if is_simulated_source(source) else "live"


@dataclass
class DailyInputs:
    """One value per (component, day), plus bookkeeping for notices."""

    values: dict[str, dict[date, float]] = field(default_factory=lambda: defaultdict(dict))
    # Which kinds of data ("live", "simulated") produced each (component, day).
    origins: dict[str, dict[date, set[str]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(set))
    )
    checkin_days: set[date] = field(default_factory=set)
    excluded_suspect: int = 0

    @property
    def data_days(self) -> set[date]:
        return {d for series in self.values.values() for d in series}

    def origin(self, day: date, components: Iterable[str] | None = None) -> Origin | None:
        """live / simulated / mixed for the values of `day` (all components by default).

        A value with no recorded origin counts as live.
        """
        kinds: set[str] = set()
        for name in self.values if components is None else components:
            if day in self.values.get(name, {}):
                kinds |= self.origins.get(name, {}).get(day) or {"live"}
        return _origin(kinds)


def _mean_by_day(pairs: Iterable[tuple[date, float]]) -> dict[date, float]:
    grouped: dict[date, list[float]] = defaultdict(list)
    for day, value in pairs:
        grouped[day].append(value)
    return {day: statistics.fmean(vals) for day, vals in grouped.items()}


def _percentile_low(values: Sequence[float], fraction: float = 0.1) -> float:
    """Nearest-rank lower percentile."""
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def build_daily_inputs(
    astronaut_id: str,
    checkins: Sequence[Checkin],
    signals: Sequence[Signal],
    vision: Sequence[VisionSession],
    co_presence: Sequence[CoPresence],
    heart_rates: Sequence[Reading],
    settings: WellbeingSettings,
) -> DailyInputs:
    """Aggregate raw inputs to daily component values.

    quality "bad" is ignored. "suspect" is excluded too but counted, so the
    response can say how many were left out.
    """
    inputs = DailyInputs()

    def usable(quality: str) -> bool:
        if quality == "suspect":
            inputs.excluded_suspect += 1
        return quality == "good"

    for c in checkins:
        inputs.checkin_days.add(c.day)
        for item in _CHECKIN_ITEMS:
            inputs.values[f"checkin.{item}"][c.day] = float(getattr(c, item))
            inputs.origins[f"checkin.{item}"][c.day].add(_source_kind(c.source))

    by_kind: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for s in signals:
        day = settings.day_of(s.recorded_at)
        if usable(s.quality):
            by_kind[s.kind].append((day, s.value))
            inputs.origins[f"signal.{s.kind}"][day].add(_source_kind(s.source))
    for kind, pairs in by_kind.items():
        inputs.values[f"signal.{kind}"].update(_mean_by_day(pairs))

    vision_pairs: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for v in vision:
        day = settings.day_of(v.started_at)
        if not usable(v.quality):
            continue
        minutes = (v.ended_at - v.started_at).total_seconds() / 60
        metrics: dict[str, float | None] = {}
        if v.fatigue:
            metrics["perclos"] = v.fatigue.perclos
            if v.neutral_ok:
                metrics["eye_openness_vs_neutral"] = v.fatigue.eye_openness_vs_neutral
            if minutes > 0 and v.fatigue.yawn_count is not None:
                metrics["yawns_per_min"] = v.fatigue.yawn_count / minutes
            if minutes > 0 and v.fatigue.nod_count is not None:
                metrics["nods_per_min"] = v.fatigue.nod_count / minutes
        # Tension deltas are relative to the day's neutral: useless without it.
        if v.tension and v.neutral_ok:
            metrics.update(v.tension.model_dump())
        if v.motion:
            metrics.update(v.motion.model_dump())
        for name, value in metrics.items():
            if value is not None and f"vision.{name}" in COMPONENTS_BY_NAME:
                vision_pairs[name].append((day, float(value)))
                inputs.origins[f"vision.{name}"][day].add(_source_kind(v.source))
    for name, pairs in vision_pairs.items():
        inputs.values[f"vision.{name}"].update(_mean_by_day(pairs))

    accompanied: dict[date, float] = defaultdict(float)
    for window in co_presence:
        day = settings.day_of(window.window_start)
        if not any(o.astronaut_id == astronaut_id for o in window.occupants):
            continue
        if not usable(window.quality):
            continue
        inputs.origins["social.accompanied_minutes"][day].add(_source_kind(window.source))
        # Max over own pairs: a lower bound that avoids double counting groups.
        seconds = max(
            (p.seconds_together for p in window.pairs if astronaut_id in (p.a, p.b)),
            default=0.0,
        )
        accompanied[day] += seconds / 60
    inputs.values["social.accompanied_minutes"].update(accompanied)

    hr_by_day: dict[date, list[float]] = defaultdict(list)
    for r in heart_rates:
        day = settings.day_of(r.recorded_at)
        if usable(r.quality):
            hr_by_day[day].append(r.value)
            inputs.origins["onboard.heart_rate_low"][day].add(_source_kind(r.source))
    for day, vals in hr_by_day.items():
        if len(vals) >= settings.min_heart_rate_readings:
            inputs.values["onboard.heart_rate_low"][day] = _percentile_low(vals)

    # Drop empty series so "has data" checks stay simple.
    inputs.values = defaultdict(dict, {k: v for k, v in inputs.values.items() if v})
    return inputs


# --- Evaluation ---


@dataclass
class ComponentEval:
    definition: ComponentDef
    baseline_median: float | None
    baseline_scale: float | None
    baseline_days: list[date]
    ready: bool
    latest_day: date | None
    latest_value: float | None
    latest_z: float | None
    # z of days after the baseline period: the only days that can be "deviant".
    z_by_day: dict[date, float]


@dataclass
class Run:
    start: date
    days: int


@dataclass
class IndicatorEval:
    kind: IndicatorKind
    status: IndicatorStatus
    z: float | None
    run: Run | None
    sources: list[WellbeingSource]
    latest_day: date | None
    components: list[ComponentEval]
    z_by_day: dict[date, float]


@dataclass
class Evaluation:
    as_of: date
    level: SupportLevel
    confidence: Confidence
    trend: Trend
    onset_date: date | None
    sustained_days: int
    discrepancy: bool
    sustained_sources: list[WellbeingSource]
    latest_day: date | None
    indicators: list[IndicatorEval]
    source_z_by_day: dict[WellbeingSource, dict[date, float]]
    checkin_baseline_days: int


def _adverse_z(value: float, median: float, scale: float, direction: AdverseDirection) -> float:
    delta = (value - median) / scale
    if direction == "low":
        return -delta
    if direction == "high":
        return delta
    return abs(delta)


def _evaluate_component(
    definition: ComponentDef,
    series: dict[date, float],
    first_day: date,
    settings: WellbeingSettings,
) -> ComponentEval:
    days = sorted(series)
    start = first_day + timedelta(days=settings.adaptation_days)
    baseline_days = [d for d in days if d >= start][: settings.baseline_days]
    ready = len(baseline_days) >= settings.baseline_min_days
    latest_day = days[-1] if days else None
    latest_value = series[latest_day] if latest_day else None

    if not ready:
        return ComponentEval(
            definition, None, None, baseline_days, False, latest_day, latest_value, None, {}
        )

    base_values = [series[d] for d in baseline_days]
    median = statistics.median(base_values)
    mad = statistics.median(abs(v - median) for v in base_values)
    scale = max(_MAD_TO_SD * mad, definition.scale_floor)
    cap = settings.z_cap

    def z_of(value: float) -> float:
        z = _adverse_z(value, median, scale, definition.adverse)
        return max(-cap, min(cap, z))

    baseline_end = baseline_days[-1]
    z_by_day = {d: z_of(series[d]) for d in days if d > baseline_end}
    latest_z = z_of(latest_value) if latest_value is not None else None
    return ComponentEval(
        definition,
        median,
        scale,
        baseline_days,
        True,
        latest_day,
        latest_value,
        latest_z,
        z_by_day,
    )


def _sustained_run(z_by_day: dict[date, float], threshold: float) -> Run | None:
    """Consecutive deviant days ending at the latest evaluated day.

    Days without data are absent from the dict, so they never break a run; a
    day with data under the threshold does.
    """
    run_days: list[date] = []
    for day in sorted(z_by_day, reverse=True):
        if z_by_day[day] >= threshold:
            run_days.append(day)
        else:
            break
    if not run_days:
        return None
    return Run(start=run_days[-1], days=len(run_days))


def _is_stale(latest: date | None, as_of: date, settings: WellbeingSettings) -> bool:
    return latest is not None and (as_of - latest).days > settings.stale_after_days


def _restrict(inputs: DailyInputs, as_of: date) -> dict[str, dict[date, float]]:
    return {
        name: {d: v for d, v in series.items() if d <= as_of}
        for name, series in inputs.values.items()
    }


def evaluate(inputs: DailyInputs, as_of: date, settings: WellbeingSettings) -> Evaluation:
    """Assess one astronaut using only the data up to and including `as_of`."""
    values = {k: v for k, v in _restrict(inputs, as_of).items() if v}
    all_days = sorted({d for series in values.values() for d in series})
    first_day = all_days[0] if all_days else as_of
    latest_day = all_days[-1] if all_days else None

    comp_evals = {
        c.component: _evaluate_component(c, values.get(c.component, {}), first_day, settings)
        for c in COMPONENTS
    }
    threshold = settings.z_threshold
    sustain = settings.sustain_days

    # Per-indicator and per-(indicator, source) daily z.
    indicators: list[IndicatorEval] = []
    source_z: dict[WellbeingSource, dict[date, float]] = {s: {} for s in SOURCES}
    for kind in INDICATOR_KINDS:
        comps = [comp_evals[c.component] for c in COMPONENTS if c.indicator == kind]
        per_day: dict[date, list[float]] = defaultdict(list)
        per_source_day: dict[tuple[WellbeingSource, date], list[float]] = defaultdict(list)
        for ce in comps:
            for day, z in ce.z_by_day.items():
                per_day[day].append(z)
                per_source_day[(ce.definition.source, day)].append(z)
        z_by_day = {d: statistics.fmean(zs) for d, zs in per_day.items()}
        for (source, day), zs in per_source_day.items():
            mean_z = statistics.fmean(zs)
            # A source's daily z is its strongest indicator signal that day.
            if day not in source_z[source] or mean_z > source_z[source][day]:
                source_z[source][day] = mean_z

        with_data = [ce for ce in comps if ce.latest_day is not None]
        ind_latest = max((ce.latest_day for ce in with_data), default=None)  # type: ignore[type-var]
        run = _sustained_run(z_by_day, threshold)
        sustained = run if run and run.days >= sustain else None
        status: IndicatorStatus
        if not with_data:
            status = "no_data"
        elif _is_stale(ind_latest, as_of, settings):
            status = "stale"
        elif not any(ce.ready for ce in comps):
            status = "baseline_pending"
        elif sustained:
            status = "attention"
        else:
            status = "ok"
        latest_z = z_by_day.get(ind_latest) if ind_latest else None
        indicators.append(
            IndicatorEval(
                kind=kind,
                status=status,
                z=latest_z,
                run=sustained if status == "attention" else None,
                sources=sorted({ce.definition.source for ce in with_data}, key=SOURCES.index),
                latest_day=ind_latest,
                components=comps,
                z_by_day=z_by_day,
            )
        )

    # Sources: freshness, readiness and sustained runs.
    source_latest: dict[WellbeingSource, date | None] = {}
    source_ready: dict[WellbeingSource, bool] = {}
    for source in SOURCES:
        comps = [ce for ce in comp_evals.values() if ce.definition.source == source]
        source_latest[source] = max(
            (ce.latest_day for ce in comps if ce.latest_day), default=None
        )
        source_ready[source] = any(ce.ready for ce in comps)
    fresh_ready = [
        s
        for s in SOURCES
        if source_ready[s]
        and source_latest[s] is not None
        and not _is_stale(source_latest[s], as_of, settings)
    ]
    runs: dict[WellbeingSource, Run] = {}
    for source in fresh_ready:
        run = _sustained_run(source_z[source], threshold)
        if run and run.days >= sustain:
            runs[source] = run
    sustained_sources = [s for s in SOURCES if s in runs]

    checkin_comps = [ce for ce in comp_evals.values() if ce.definition.source == "checkin"]
    checkin_baseline_days = max((len(ce.baseline_days) for ce in checkin_comps), default=0)

    level: SupportLevel
    discrepancy = False
    if not all_days:
        level = "no_data"
    elif not any(ce.ready for ce in comp_evals.values()):
        level = "baseline_pending"
    elif _is_stale(latest_day, as_of, settings):
        level = "stale"
    else:
        passive = [s for s in sustained_sources if s != "checkin"]
        discrepancy = "checkin" in fresh_ready and "checkin" not in runs and bool(passive)
        if len(sustained_sources) >= 2:
            level = "needs_support"
        elif sustained_sources:
            level = "attention"
        else:
            level = "ok"

    onset = min((runs[s].start for s in sustained_sources), default=None)
    if level not in ("attention", "needs_support"):
        onset = None
        sustained_sources = []
    sustained_days = (latest_day - onset).days + 1 if onset and latest_day else 0

    confidence: Confidence
    count = len(sustained_sources) if sustained_sources else len(fresh_ready)
    confidence = "high" if count >= 3 else "medium" if count == 2 else "low"

    trend = _trend(indicators, settings) if level not in ("no_data", "stale") else "unknown"

    return Evaluation(
        as_of=as_of,
        level=level,
        confidence=confidence,
        trend=trend,
        onset_date=onset,
        sustained_days=sustained_days,
        discrepancy=discrepancy,
        sustained_sources=sustained_sources,
        latest_day=latest_day,
        indicators=indicators,
        source_z_by_day=source_z,
        checkin_baseline_days=checkin_baseline_days,
    )


def overall_z_by_day(indicators: Sequence[IndicatorEval]) -> dict[date, float]:
    per_day: dict[date, list[float]] = defaultdict(list)
    for ind in indicators:
        for day, z in ind.z_by_day.items():
            per_day[day].append(z)
    return {d: statistics.fmean(zs) for d, zs in per_day.items()}


def _trend(indicators: Sequence[IndicatorEval], settings: WellbeingSettings) -> Trend:
    overall = overall_z_by_day(indicators)
    days = sorted(overall)
    window = settings.trend_window_days
    if len(days) < 2 * window:
        return "unknown"
    recent = statistics.fmean(overall[d] for d in days[-window:])
    previous = statistics.fmean(overall[d] for d in days[-2 * window : -window])
    delta = recent - previous
    if delta > settings.trend_min_delta:
        return "worsening"
    if delta < -settings.trend_min_delta:
        return "improving"
    return "stable"


# --- Texts (Spanish, support language, never clinical labels) ---


def support_notes(ev: Evaluation, settings: WellbeingSettings) -> list[str]:
    notes: list[str] = []
    onset = ev.onset_date.isoformat() if ev.onset_date else None
    if ev.level == "needs_support":
        labels = ", ".join(SOURCE_LABELS[s] for s in ev.sustained_sources)
        notes.append(
            f"Varias fuentes ({labels}) muestran cambios sostenidos desde el {onset}. "
            "Puede ayudar hablarlo con alguien de confianza de la tripulación."
        )
        notes.append(
            "Si quieres, puedes enviar un resumen al psicólogo en Tierra. "
            "Sólo se envía con tu consentimiento."
        )
    elif ev.level == "attention":
        labels = ", ".join(SOURCE_LABELS[s] for s in ev.sustained_sources)
        notes.append(
            f"Una fuente ({labels}) muestra un cambio sostenido desde el {onset}. "
            "Puede ser útil tomarse un momento para revisar cómo te sientes."
        )
    elif ev.level == "ok":
        notes.append("Sin cambios sostenidos respecto a tu línea base.")
    elif ev.level == "baseline_pending":
        missing = max(0, settings.baseline_min_days - ev.checkin_baseline_days)
        notes.append(
            "Construyendo tu línea base personal: "
            f"faltan {missing} día(s) de checklist para empezar a comparar."
        )
    elif ev.level == "stale":
        last = ev.latest_day.isoformat() if ev.latest_day else "-"
        notes.append(f"No hay datos recientes desde el {last}.")
    else:
        notes.append("Aún no hay datos de bienestar. Empieza con el checklist diario.")
    if ev.discrepancy:
        notes.append(
            "Tu checklist no muestra cambios, pero otras señales sí. "
            "No significa nada por sí solo: es una invitación a revisar cómo estás."
        )
    return notes


def origin_counts(inputs: DailyInputs, as_of: date) -> Counter[str]:
    """Days with data up to `as_of`, by origin: live, simulated or mixed (disjoint)."""
    return Counter(inputs.origin(d) for d in inputs.data_days if d <= as_of)


def data_notices(inputs: DailyInputs, as_of: date) -> list[str]:
    notices: list[str] = []
    counts = origin_counts(inputs, as_of)
    if counts["simulated"] or counts["mixed"]:
        notices.append(
            f"Días con datos: {counts['live']} en vivo, {counts['simulated']} simulados, "
            f"{counts['mixed']} mixtos (en vivo + simulados)."
        )
    if inputs.excluded_suspect:
        notices.append(
            f"{inputs.excluded_suspect} dato(s) con calidad dudosa excluidos del análisis."
        )
    return notices
