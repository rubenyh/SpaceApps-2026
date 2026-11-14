import type { AstronautStatus, Reading, SensorStatus } from "../api/types";
import { listReadings } from "../api/readings";
import { getAstronautStatus } from "../api/status";
import { LineChart } from "../components/LineChart";
import { SensorCard } from "../components/SensorCard";
import { ServiceBanner } from "../components/ServiceBanner";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { shownStatus } from "../lib/estado";
import { chronological, rangeText } from "../lib/format";
import { findSensor, liveAge } from "../lib/sensors";

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

interface VitalProps {
  title: string;
  organ: string;
  sensor: SensorStatus | null;
  readings: Reading[];
  age: number | null;
  windowEnd: number;
  loaded: boolean;
  offline: boolean;
}

function Vital({ title, organ, sensor, readings, age, windowEnd, loaded, offline }: VitalProps) {
  const config = sensor?.config ?? null;
  const range = config ? rangeText(config) : null;
  // Only plot numeric readings in the configured unit (or any unit if none is configured).
  const points = chronological(readings)
    .filter((r) => r.value !== null && (!config?.unit || r.unit === config.unit))
    .map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }));

  return (
    <SensorCard
      title={title}
      organ={organ}
      sensor={sensor}
      ageSeconds={age}
      loaded={loaded}
      offline={offline}
      size="lg"
      showSource
    >
      <div className="chart-block">
        <span className="caption">Últimos 15 minutos · horas en UTC</span>
        <LineChart
          points={points}
          start={windowEnd - WINDOW_MS}
          end={windowEnd}
          normalMin={config?.normal_min ?? null}
          normalMax={config?.normal_max ?? null}
          zoneLabel={range ? `Normal ${range}${config?.provisional ? " · PROV." : ""}` : undefined}
          status={shownStatus(sensor, offline)}
          width={572}
          height={250}
          label={`${title}, últimos 15 minutos`}
          emptyText="Sin lecturas en los últimos 15 minutos"
        />
      </div>
    </SensorCard>
  );
}

export function VitalesScreen({ astronautId }: Props) {
  const poll = usePolling(
    `vitales:${astronautId}`,
    (signal) => fetchVitals(astronautId, signal),
    5000,
  );
  const now = useNow(1000);
  const { data, error, updatedAt, refresh } = poll;
  const loaded = data !== null;
  const offline = error !== null;
  const heart = findSensor(data?.status, "heart_rate");
  const spo2 = findSensor(data?.status, "spo2");
  // Window ends at the fetch time so the trace matches the data that was fetched.
  const windowEnd = data?.fetchedAt ?? now;

  return (
    <div className="screen">
      <ServiceBanner error={error} updatedAt={updatedAt} onRetry={refresh} />
      <div className="vitales__grid">
        <Vital
          title="Pulso"
          organ="Corazón"
          sensor={heart}
          readings={data?.heart ?? []}
          age={liveAge(heart, updatedAt, now)}
          windowEnd={windowEnd}
          loaded={loaded}
          offline={offline}
        />
        <Vital
          title="Oxígeno en sangre"
          organ="SpO₂ · pulmones"
          sensor={spo2}
          readings={data?.spo2 ?? []}
          age={liveAge(spo2, updatedAt, now)}
          windowEnd={windowEnd}
          loaded={loaded}
          offline={offline}
        />
      </div>
    </div>
  );
}
