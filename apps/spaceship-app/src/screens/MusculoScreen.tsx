import { useState } from "react";
import type { AstronautStatus, Reading } from "../api/types";
import { listReadings } from "../api/readings";
import { getAstronautStatus } from "../api/status";
import { AgeLabel } from "../components/AgeLabel";
import { ErrorNotice } from "../components/ErrorNotice";
import { Panel } from "../components/Panel";
import { StatusBadge } from "../components/StatusBadge";
import { TrendChart } from "../components/TrendChart";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import {
  chronological,
  formatNumber,
  formatSigned,
  formatUtcDateTime,
  readingValueText,
  unitLabel,
} from "../lib/format";
import { findSensor, liveAge, stateBoxClass } from "../lib/sensors";

interface Props {
  astronautId: string;
}

type RangeKey = "7d" | "30d" | "all";
const RANGES: { key: RangeKey; label: string }[] = [
  { key: "7d", label: "7 D" },
  { key: "30d", label: "30 D" },
  { key: "all", label: "TODO" },
];
const DAY = 86_400_000;

interface MuscleData {
  status: AstronautStatus;
  readings: Reading[];
}

async function fetchMuscle(astronautId: string, signal: AbortSignal): Promise<MuscleData> {
  const [status, readings] = await Promise.all([
    getAstronautStatus(astronautId, signal),
    listReadings({ astronaut_id: astronautId, kind: "muscle_density", limit: 1000 }, signal),
  ]);
  return { status, readings };
}

export function MusculoScreen({ astronautId }: Props) {
  const [range, setRange] = useState<RangeKey>("30d");
  const poll = usePolling(
    `musculo:${astronautId}`,
    (signal) => fetchMuscle(astronautId, signal),
    30_000,
  );
  const now = useNow(1000);
  const { data, error, updatedAt } = poll;
  const loaded = data !== null;

  const sensor = findSensor(data?.status, "muscle_density");
  const status = sensor?.status ?? "no_data";
  const latest = sensor?.latest ?? null;

  // Unit is undefined for this sensor: plot only readings in the latest reading's unit.
  const all = chronological((data?.readings ?? []).filter((r) => r.value !== null));
  const unit = latest?.unit ?? all[all.length - 1]?.unit ?? null;
  const sameUnit = all.filter((r) => r.unit === unit);
  const excluded = all.length - sameUnit.length;
  const points = sameUnit.map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }));

  const first = sameUnit[0] ?? null;
  const last = sameUnit[sameUnit.length - 1] ?? null;
  const change =
    first && last && first !== last ? (last.value as number) - (first.value as number) : null;

  const end = now;
  const start =
    range === "7d"
      ? end - 7 * DAY
      : range === "30d"
        ? end - 30 * DAY
        : points.length > 0
          ? Math.min(points[0].t, end - DAY)
          : end - DAY;

  return (
    <div className="screen">
      <ErrorNotice error={error} hasData={loaded} />
      <div className={error && loaded ? "dimmed" : ""}>
        <Panel
          title="DENSIDAD MUSCULAR"
          aside={loaded ? <StatusBadge status={status} /> : <span className="badge">[ … ]</span>}
          className={stateBoxClass(status)}
        >
          <div className="vital__value">
            <span className="value-lg">{status === "no_data" ? "---" : readingValueText(latest)}</span>
            {latest && status !== "no_data" ? (
              <span className="unit">{unitLabel(latest.unit)}</span>
            ) : null}
            <AgeLabel
              seconds={status === "no_data" ? null : liveAge(sensor, updatedAt, now)}
              emphasis={status === "stale"}
            />
          </div>
          <TrendChart
            points={points}
            start={start}
            end={end}
            label="Densidad muscular"
            emptyText="SIN LECTURAS EN ESTE PERIODO"
          />
          <div className="toolbar">
            <span className="muted">fechas en UTC</span>
            <div className="btn-group" role="group" aria-label="Periodo">
              {RANGES.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  className={range === r.key ? "btn btn--active" : "btn"}
                  aria-pressed={range === r.key}
                  onClick={() => setRange(r.key)}
                >
                  {range === r.key ? `[${r.label}]` : r.label}
                </button>
              ))}
            </div>
          </div>
          <dl className="facts">
            <dt>CAMBIO DESDE LA PRIMERA LECTURA</dt>
            <dd>
              {change !== null && first ? (
                <>
                  {formatSigned(change)} {unitLabel(unit)}{" "}
                  <span className="muted">
                    (primera: {formatNumber(first.value as number)} {unitLabel(unit)},{" "}
                    {formatUtcDateTime(first.recorded_at)} UTC)
                  </span>
                </>
              ) : (
                "--- (se necesitan al menos dos lecturas)"
              )}
            </dd>
            <dt>LECTURAS</dt>
            <dd>
              {sameUnit.length}
              {excluded > 0
                ? ` · ${excluded} con otra unidad no se representan ni se comparan`
                : ""}
            </dd>
          </dl>
          <p className="note">Método de medición y rango de referencia: sin definir.</p>
        </Panel>
      </div>
    </div>
  );
}
