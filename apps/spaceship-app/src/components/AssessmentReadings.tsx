import type { AstronautStatus, Quality, SensorKind, SensorStatus, SnapshotReading } from "../api/types";
import { useNow } from "../hooks/useNow";
import { SENSOR_LABELS, formatAge, formatNumber, formatUtcDateTime, readingValueText, unitLabel } from "../lib/format";
import { URINE_KINDS, aggregateUrine, findSensor, isSimulatedSource, liveAge } from "../lib/sensors";
import { QualityMark } from "./QualityMark";
import { STATE_LABELS, StateIcon, type VisualState } from "./StatusPill";
import { withSub2 } from "./Sub2";

interface RowProps {
  label: string;
  /** Icon before the label; null keeps the slot empty so rows stay aligned. */
  icon: VisualState | null;
  /** State or freshness word, drawn as its own mark. */
  mark: string;
  /** Modifier for colour: a VisualState or "current". */
  tone: string;
  value: string;
  unit: string;
  /** Formatted age, or "Never measured" / "…". */
  age: string;
  quality: Quality | null;
  source: string | null;
  simulated: boolean;
}

/** One reading row. Hardware and simulated data look the same except for the "Simulated" badge. */
function Row({ label, icon, mark, tone, value, unit, age, quality, source, simulated }: RowProps) {
  return (
    <li className={`areadings__row areadings__row--${tone}`}>
      <span className="areadings__name">
        {icon ? <StateIcon state={icon} /> : <span className="areadings__noicon" aria-hidden="true" />}
        {withSub2(label)}
      </span>
      <span className="areadings__value">
        {value}
        {unit ? <span className="areadings__unit"> {unit}</span> : null}
      </span>
      <span className="areadings__meta">
        <span className="areadings__mark">{mark}</span>
        <span className="areadings__age">{age}</span>
        {quality ? <QualityMark quality={quality} /> : null}
        {source ? <span className="areadings__source">{source}</span> : null}
        {simulated ? <span className="areadings__sim">Simulated</span> : null}
      </span>
    </li>
  );
}

const URINE_SHORT: Partial<Record<SensorKind, string>> = {
  urine_ph: "pH",
  urine_salinity: "salinity",
  urine_color: "color",
  urine_temperature: "temp.",
};

function valueWithUnit(s: SensorStatus): string {
  const unit = unitLabel(s.latest?.unit);
  return `${readingValueText(s.latest)}${unit ? ` ${unit}` : ""}`;
}

/** Live readings from the status poll: always the same five rows, missing ones say so. */
export function LiveReadings({ status, updatedAt }: { status: AstronautStatus | null; updatedAt: number | null }) {
  const now = useNow(1000);
  const ageText = (age: number | null) => (status === null ? "…" : age === null ? "Never measured" : formatAge(age));

  const single = (kind: SensorKind, label: string): RowProps => {
    const s = findSensor(status, kind);
    const st: VisualState = s?.status ?? "no_data";
    const latest = s?.latest ?? null;
    return {
      label,
      icon: st,
      mark: STATE_LABELS[st],
      tone: st,
      value: readingValueText(latest),
      unit: latest ? unitLabel(latest.unit) : "",
      age: ageText(latest ? liveAge(s, updatedAt, now) : null),
      quality: latest?.quality ?? null,
      source: latest?.source ?? null,
      simulated: isSimulatedSource(latest?.source),
    };
  };

  const urine = URINE_KINDS.map((k) => findSensor(status, k));
  const measured = urine.filter((s): s is SensorStatus => s?.latest != null);
  // Newest urine measurement carries the age, quality and source of the row.
  const newest = measured.reduce<SensorStatus | null>(
    (best, s) => (best === null || (s.age_seconds ?? Infinity) < (best.age_seconds ?? Infinity) ? s : best),
    null,
  );
  const urineState: VisualState = aggregateUrine(urine);
  const urineRow: RowProps = {
    label: "Urine",
    icon: urineState,
    mark: STATE_LABELS[urineState],
    tone: urineState,
    value: measured.length > 0 ? measured.map((s) => `${URINE_SHORT[s.kind]} ${valueWithUnit(s)}`).join(" · ") : "---",
    unit: "",
    age: ageText(newest ? liveAge(newest, updatedAt, now) : null),
    quality: newest?.latest?.quality ?? null,
    source: newest?.latest?.source ?? null,
    simulated: measured.some((s) => isSimulatedSource(s.latest?.source)),
  };

  const rows = [
    single("heart_rate", "Heart rate"),
    single("spo2", "Oxygen (SpO₂)"),
    urineRow,
    single("muscle_density", "Muscle"),
    single("urine_radiation_marker", "Radiation marker"),
  ];
  return (
    <section className="areadings" aria-label="Live readings">
      <span className="caption areadings__head">Live · status poll</span>
      <ul className="areadings__list">
        {rows.map((r) => (
          <Row key={r.label} {...r} />
        ))}
      </ul>
    </section>
  );
}

const FRESHNESS: Record<SnapshotReading["freshness"], { mark: string; icon: VisualState | null }> = {
  current: { mark: "Current", icon: null },
  stale: { mark: "Old data", icon: "stale" },
  future: { mark: "Clock ahead", icon: "future" },
};

/** Readings the assessment was based on, frozen at assessment time. */
export function SnapshotReadings({
  readings,
  assessedAt,
  title,
}: {
  readings: SnapshotReading[];
  assessedAt?: string | null;
  title?: string;
}) {
  const heading = `${title ?? "Assessment snapshot"}${assessedAt ? ` · ${formatUtcDateTime(assessedAt)} UTC` : ""}`;
  return (
    <section className="areadings" aria-label={heading}>
      <span className="caption areadings__head">{heading}</span>
      {readings.length === 0 ? (
        <p className="caption">No readings in this snapshot.</p>
      ) : (
        <ul className="areadings__list">
          {readings.map((r) => {
            const f = FRESHNESS[r.freshness];
            return (
              <Row
                key={r.id}
                label={SENSOR_LABELS[r.kind as SensorKind] ?? r.kind}
                icon={f.icon}
                mark={f.mark}
                tone={r.freshness}
                value={r.value_text ?? (r.value !== null ? formatNumber(r.value) : "---")}
                unit={unitLabel(r.unit)}
                age={formatAge(r.age_seconds)}
                quality={r.quality}
                source={r.source}
                simulated={r.simulated || isSimulatedSource(r.source)}
              />
            );
          })}
        </ul>
      )}
    </section>
  );
}
