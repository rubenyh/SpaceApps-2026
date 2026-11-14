import { useState } from "react";
import type { AstronautStatus, Reading } from "../api/types";
import { listReadings } from "../api/readings";
import { getAstronautStatus } from "../api/status";
import type { Point } from "../components/chartScale";
import { LineChart } from "../components/LineChart";
import { Panel } from "../components/Panel";
import { SegmentedControl } from "../components/SegmentedControl";
import { SensorCard } from "../components/SensorCard";
import { ServiceBanner } from "../components/ServiceBanner";
import { StateIcon } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { shownStatus } from "../lib/estado";
import { chronological, formatDuration, formatSigned, rangeText, unitLabel } from "../lib/format";
import { findSensor, liveAge } from "../lib/sensors";

interface Props {
  astronautId: string;
}

type RangeKey = "7d" | "30d" | "all";
const RANGES: { key: RangeKey; label: string }[] = [
  { key: "7d", label: "7 D" },
  { key: "30d", label: "30 D" },
  { key: "all", label: "Todo" },
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
  const { data, error, updatedAt, refresh } = poll;
  const loaded = data !== null;
  const offline = error !== null;

  const sensor = findSensor(data?.status, "muscle_density");
  const latest = sensor?.latest ?? null;
  const age = liveAge(sensor, updatedAt, now);

  // Unit is undefined for this sensor: plot only readings in the latest reading's unit.
  const all = chronological((data?.readings ?? []).filter((r) => r.value !== null));
  const unit = latest?.unit ?? all[all.length - 1]?.unit ?? null;
  const sameUnit = all.filter((r) => r.unit === unit);
  const excluded = all.length - sameUnit.length;
  const points = sameUnit.map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }));

  const first: Point | null = points[0] ?? null;
  const last: Point | null = points[points.length - 1] ?? null;
  const first30 = points.find((p) => p.t >= now - 30 * DAY) ?? null;
  const delta = (from: Point | null) =>
    from && last && from !== last ? `${formatSigned(last.v - from.v)} ${unitLabel(unit)}` : "---";

  const end = now;
  const start =
    range === "7d"
      ? end - 7 * DAY
      : range === "30d"
        ? end - 30 * DAY
        : first
          ? Math.min(first.t, end - DAY)
          : end - DAY;

  const hasRange = sensor !== null && rangeText(sensor.config) !== null;
  const ttl = sensor?.config.stale_after_seconds ?? null;
  const fresh = sensor !== null && sensor.status !== "stale" && sensor.status !== "no_data";

  return (
    <div className="screen">
      <ServiceBanner error={error} updatedAt={updatedAt} onRetry={refresh} />
      <div className="musculo__grid">
        <div className="musculo__side">
          <SensorCard
            title="Densidad muscular"
            organ="Extremidades"
            sensor={sensor}
            ageSeconds={age}
            loaded={loaded}
            offline={offline}
          >
            <div className="stats">
              <div className="stat">
                <span>Desde la primera lectura</span>
                <strong>{delta(first)}</strong>
              </div>
              <div className="stat">
                <span>En los últimos 30 días</span>
                <strong>{delta(first30)}</strong>
              </div>
            </div>
          </SensorCard>
          {loaded && !hasRange ? (
            <div className="infobox infobox--no_range">
              <StateIcon state="no_range" size={18} />
              <div>
                <strong>Rango de referencia aún sin definir</strong>
                <span>
                  Usa esta pantalla para ver si el valor baja con las semanas, no para juzgar una
                  lectura aislada.
                </span>
              </div>
            </div>
          ) : null}
          {fresh && ttl !== null && age !== null && age < ttl ? (
            <div className="infobox">
              <StateIcon state="stale" />
              <span>
                Pasará a <strong>dato viejo</strong> en {formatDuration(ttl - age)} (vigencia:{" "}
                {formatDuration(ttl)})
              </span>
            </div>
          ) : null}
        </div>
        <Panel
          title="Tendencia"
          aside={<SegmentedControl label="Periodo" options={RANGES} value={range} onChange={setRange} />}
        >
          <div className="panel__caption">
            <span className="caption">
              {unit ? `Valor en ${unitLabel(unit)}` : "Valor"} · {sameUnit.length} lecturas · fechas en UTC
              {excluded > 0 ? ` · ${excluded} con otra unidad no se representan ni se comparan` : ""}
            </span>
            <span className="caption caption--legend">
              <span className="legend-line" aria-hidden="true" />
              Primera lectura
            </span>
          </div>
          <LineChart
            points={points}
            start={start}
            end={end}
            status={loaded ? shownStatus(sensor, offline) : undefined}
            showPoints
            baseline={first?.v ?? null}
            width={790}
            height={410}
            label="Densidad muscular"
            emptyText="Sin lecturas en este periodo"
          />
        </Panel>
      </div>
    </div>
  );
}
