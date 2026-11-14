import { useState } from "react";
import type { AstronautStatus, Reading, SensorKind, SensorStatus } from "../api/types";
import { listReadings } from "../api/readings";
import { getAstronautStatus } from "../api/status";
import { AgeLabel } from "../components/AgeLabel";
import { ColorSwatch } from "../components/ColorSwatch";
import { ErrorNotice } from "../components/ErrorNotice";
import { Panel } from "../components/Panel";
import { RadiationPanel } from "../components/RadiationPanel";
import { StatusBadge } from "../components/StatusBadge";
import { TrendChart } from "../components/TrendChart";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { chronological, rangeText, readingValueText, unitLabel } from "../lib/format";
import { URINE_KINDS, findSensor, liveAge, stateBoxClass } from "../lib/sensors";

interface Props {
  astronautId: string;
}

type TrendKind = "urine_salinity" | "urine_ph";
const TREND_OPTIONS: { kind: TrendKind; label: string }[] = [
  { kind: "urine_salinity", label: "SALINIDAD" },
  { kind: "urine_ph", label: "pH" },
];
const TREND_DAYS = 14;
const DAY = 86_400_000;

interface UrineData {
  status: AstronautStatus;
  salinity: Reading[];
  ph: Reading[];
}

async function fetchUrine(astronautId: string, signal: AbortSignal): Promise<UrineData> {
  const since = new Date(Date.now() - TREND_DAYS * DAY).toISOString();
  const [status, salinity, ph] = await Promise.all([
    getAstronautStatus(astronautId, signal),
    listReadings(
      { astronaut_id: astronautId, kind: "urine_salinity", since, limit: 1000 },
      signal,
    ),
    listReadings({ astronaut_id: astronautId, kind: "urine_ph", since, limit: 1000 }, signal),
  ]);
  return { status, salinity, ph };
}

const ROW_LABELS: Partial<Record<SensorKind, string>> = {
  urine_ph: "pH",
  urine_salinity: "SALINIDAD",
  urine_color: "COLOR",
  urine_temperature: "TEMPERATURA",
};

interface RowProps {
  kind: SensorKind;
  sensor: SensorStatus | null;
  age: number | null;
  loaded: boolean;
}

function UrineRow({ kind, sensor, age, loaded }: RowProps) {
  const status = sensor?.status ?? "no_data";
  const latest = sensor?.latest ?? null;
  const config = sensor?.config ?? null;
  const role = config?.range_role ?? "health";
  const visual = role === "sample_validity" && status === "alert" ? "doubtful" : status;
  const range = config ? rangeText(config) : null;
  const noData = status === "no_data";

  return (
    <div className={`urine-row ${stateBoxClass(visual)}`}>
      <div className="urine-row__label">{ROW_LABELS[kind]}</div>
      <div className="urine-row__value">
        {noData ? (
          <span className="value-md">---</span>
        ) : kind === "urine_color" ? (
          <span className="value-md">
            <ColorSwatch value={latest?.value_text} />
          </span>
        ) : (
          <>
            <span className="value-md">{readingValueText(latest)}</span>
            {latest ? (
              <span className="unit">{unitLabel(latest.unit)}</span>
            ) : null}
          </>
        )}
      </div>
      <div className="urine-row__state">
        {loaded ? <StatusBadge status={status} rangeRole={role} /> : <span className="badge">[ … ]</span>}
      </div>
      <div className="urine-row__meta muted">
        <AgeLabel seconds={noData ? null : age} emphasis={status === "stale"} />
        {range ? (
          <span>
            {role === "sample_validity" ? "validez " : "rango "}
            {range}
            {config?.provisional ? " · PROV." : ""}
            {config?.range_source ? ` (${config.range_source})` : ""}
          </span>
        ) : (
          <span>sin rango</span>
        )}
      </div>
    </div>
  );
}

export function OrinaScreen({ astronautId }: Props) {
  const [trend, setTrend] = useState<TrendKind>("urine_salinity");
  const poll = usePolling(
    `orina:${astronautId}`,
    (signal) => fetchUrine(astronautId, signal),
    30_000,
  );
  const now = useNow(1000);
  const { data, error, updatedAt } = poll;
  const loaded = data !== null;

  const sensors = URINE_KINDS.map((k) => findSensor(data?.status, k));
  const ages = sensors
    .map((s) => liveAge(s, updatedAt, now))
    .filter((a): a is number => a !== null);
  const lastSample = ages.length > 0 ? Math.min(...ages) : null;
  const radiation = findSensor(data?.status, "urine_radiation_marker");

  const trendSensor = findSensor(data?.status, trend);
  const trendReadings = chronological(
    (trend === "urine_salinity" ? data?.salinity : data?.ph) ?? [],
  ).filter((r) => r.value !== null);
  // Salinity has no defined unit: plot only readings sharing the newest reading's unit.
  const trendUnit = trendReadings[trendReadings.length - 1]?.unit ?? null;
  const trendSame = trendReadings.filter((r) => r.unit === trendUnit);
  const trendExcluded = trendReadings.length - trendSame.length;
  const trendLabel = TREND_OPTIONS.find((o) => o.kind === trend)?.label ?? "";

  return (
    <div className="screen">
      <ErrorNotice error={error} hasData={loaded} />
      <div className={`grid-orina ${error && loaded ? "dimmed" : ""}`}>
        <Panel title="ORINA · ÚLTIMA MUESTRA" aside={<AgeLabel seconds={lastSample} prefix="última muestra:" />}>
          <div className="urine-rows">
            {URINE_KINDS.map((k, i) => (
              <UrineRow
                key={k}
                kind={k}
                sensor={sensors[i]}
                age={liveAge(sensors[i], updatedAt, now)}
                loaded={loaded}
              />
            ))}
          </div>
          <p className="muted">
            La temperatura indica si la muestra es válida; fuera de rango se marca MUESTRA DUDOSA, no
            es una alerta de salud.
          </p>
          <div className="trend">
            <div className="trend__title">
              {trendLabel} · {TREND_DAYS} DÍAS
              {trendUnit ? ` · ${unitLabel(trendUnit)}` : ""}
            </div>
            <TrendChart
              points={trendSame.map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }))}
              start={now - TREND_DAYS * DAY}
              end={now}
              normalMin={trendSensor?.config.normal_min ?? null}
              normalMax={trendSensor?.config.normal_max ?? null}
              label={`${trendLabel}, ${TREND_DAYS} días`}
              emptyText="SIN LECTURAS EN 14 DÍAS"
            />
            <div className="toolbar">
              <div className="btn-group" role="group" aria-label="Serie">
                {TREND_OPTIONS.map((o) => (
                  <button
                    key={o.kind}
                    type="button"
                    className={trend === o.kind ? "btn btn--active" : "btn"}
                    aria-pressed={trend === o.kind}
                    onClick={() => setTrend(o.kind)}
                  >
                    {trend === o.kind ? `[${o.label}]` : o.label}
                  </button>
                ))}
              </div>
              <span className="muted">
                fechas en UTC
                {trendExcluded > 0 ? ` · ${trendExcluded} lecturas con otra unidad no se muestran` : ""}
              </span>
            </div>
          </div>
        </Panel>
        <RadiationPanel sensor={radiation} ageSeconds={liveAge(radiation, updatedAt, now)} />
      </div>
    </div>
  );
}
