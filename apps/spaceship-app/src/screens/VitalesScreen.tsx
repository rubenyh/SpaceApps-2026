import type { AstronautStatus, Reading, SensorStatus } from "../api/types";
import { listReadings } from "../api/readings";
import { getAstronautStatus } from "../api/status";
import { AgeLabel } from "../components/AgeLabel";
import { ErrorNotice } from "../components/ErrorNotice";
import { Panel } from "../components/Panel";
import { ScopeChart } from "../components/ScopeChart";
import { SegmentedBar } from "../components/SegmentedBar";
import { StatusBadge } from "../components/StatusBadge";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { chronological, rangeText, readingValueText, unitLabel } from "../lib/format";
import { findSensor, liveAge, stateBoxClass } from "../lib/sensors";

interface Props {
  astronautId: string;
}

const WINDOW_MS = 15 * 60 * 1000;

interface VitalsData {
  status: AstronautStatus;
  heart: Reading[];
  spo2: Reading[];
  fetchedAt: number;
}

async function fetchVitals(astronautId: string, signal: AbortSignal): Promise<VitalsData> {
  const fetchedAt = Date.now();
  const since = new Date(fetchedAt - WINDOW_MS).toISOString();
  const [status, heart, spo2] = await Promise.all([
    getAstronautStatus(astronautId, signal),
    listReadings({ astronaut_id: astronautId, kind: "heart_rate", since, limit: 1000 }, signal),
    listReadings({ astronaut_id: astronautId, kind: "spo2", since, limit: 1000 }, signal),
  ]);
  return { status, heart, spo2, fetchedAt };
}

interface VitalPanelProps {
  title: string;
  sensor: SensorStatus | null;
  readings: Reading[];
  age: number | null;
  windowEnd: number;
  loaded: boolean;
}

function VitalPanel({ title, sensor, readings, age, windowEnd, loaded }: VitalPanelProps) {
  const status = sensor?.status ?? "no_data";
  const latest = sensor?.latest ?? null;
  const config = sensor?.config ?? null;
  const range = config ? rangeText(config) : null;
  // Only plot numeric readings in the configured unit (or any unit if none is configured).
  const points = chronological(readings)
    .filter((r) => r.value !== null && (!config?.unit || r.unit === config.unit))
    .map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }));
  const latestNumeric =
    latest && latest.value !== null && status !== "stale" ? latest.value : null;

  return (
    <Panel
      title={title}
      aside={loaded ? <StatusBadge status={status} /> : <span className="badge">[ … ]</span>}
      className={`vital ${stateBoxClass(status)}`}
    >
      <div className="vital__value">
        <span className="value-lg">{status === "no_data" ? "---" : readingValueText(latest)}</span>
        {latest && status !== "no_data" ? <span className="unit">{unitLabel(latest.unit)}</span> : null}
        <AgeLabel seconds={status === "no_data" ? null : age} emphasis={status === "stale"} />
      </div>
      <ScopeChart
        points={points}
        windowStart={windowEnd - WINDOW_MS}
        windowEnd={windowEnd}
        normalMin={config?.normal_min ?? null}
        normalMax={config?.normal_max ?? null}
        label={title}
        emptyText="SIN LECTURAS EN LOS ÚLTIMOS 15 MIN"
      />
      <div className="vital__caption muted">últimos 15 min · líneas discontinuas = rango</div>
      <div className="vital__range">
        {range ? (
          <>
            RANGO {range}
            {config?.provisional ? (
              <>
                {" · "}
                <span className="tag">PROV.</span>
                {config.range_source ? ` (${config.range_source})` : ""}
              </>
            ) : null}
          </>
        ) : (
          "SIN RANGO"
        )}
      </div>
      <SegmentedBar
        value={latestNumeric}
        normalMin={config?.normal_min ?? null}
        normalMax={config?.normal_max ?? null}
        label={title}
      />
    </Panel>
  );
}

export function VitalesScreen({ astronautId }: Props) {
  const poll = usePolling(
    `vitales:${astronautId}`,
    (signal) => fetchVitals(astronautId, signal),
    5000,
  );
  const now = useNow(1000);
  const { data, error, updatedAt } = poll;
  const loaded = data !== null;
  const heart = findSensor(data?.status, "heart_rate");
  const spo2 = findSensor(data?.status, "spo2");
  // Window ends at the fetch time so the trace matches the data that was fetched.
  const windowEnd = data?.fetchedAt ?? now;

  return (
    <div className="screen">
      <ErrorNotice error={error} hasData={loaded} />
      <div className={`grid-2 ${error && loaded ? "dimmed" : ""}`}>
        <VitalPanel
          title="PULSO"
          sensor={heart}
          readings={data?.heart ?? []}
          age={liveAge(heart, updatedAt, now)}
          windowEnd={windowEnd}
          loaded={loaded}
        />
        <VitalPanel
          title="SpO₂"
          sensor={spo2}
          readings={data?.spo2 ?? []}
          age={liveAge(spo2, updatedAt, now)}
          windowEnd={windowEnd}
          loaded={loaded}
        />
      </div>
    </div>
  );
}
