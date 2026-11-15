import { useState } from "react";
import type { AstronautStatus, Reading } from "../api/types";
import { listReadings } from "../api/readings";
import { getAstronautStatus } from "../api/status";
import { LineChart } from "../components/LineChart";
import { Panel } from "../components/Panel";
import { RadiationPanel } from "../components/RadiationPanel";
import { SegmentedControl } from "../components/SegmentedControl";
import { SensorCard } from "../components/SensorCard";
import { ServiceBanner } from "../components/ServiceBanner";
import { StateIcon } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { chronological, formatAge, rangeText, unitLabel } from "../lib/format";
import { URINE_KINDS, findSensor, liveAge } from "../lib/sensors";

interface Props {
  astronautId: string;
}

type TrendKind = "urine_salinity" | "urine_ph";
const TREND_OPTIONS: { key: TrendKind; label: string }[] = [
  { key: "urine_salinity", label: "Salinity" },
  { key: "urine_ph", label: "pH" },
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

// Same order as URINE_KINDS.
const CARDS = [
  { title: "pH", organ: "Urine acidity" },
  { title: "Salinity", organ: "Salt concentration" },
  { title: "Color", organ: "Sample in its real color" },
  { title: "Temperature", organ: "Sample validity" },
];

export function OrinaScreen({ astronautId }: Props) {
  const [trend, setTrend] = useState<TrendKind>("urine_salinity");
  const poll = usePolling(
    `orina:${astronautId}`,
    (signal) => fetchUrine(astronautId, signal),
    30_000,
  );
  const now = useNow(1000);
  const { data, error, updatedAt, refresh } = poll;
  const loaded = data !== null;
  const offline = error !== null;

  const sensors = URINE_KINDS.map((k) => findSensor(data?.status, k));
  const ages = sensors
    .map((s) => liveAge(s, updatedAt, now))
    .filter((a): a is number => a !== null);
  const lastSample = ages.length > 0 ? Math.min(...ages) : null;
  const anyStale = sensors.some((s) => s?.status === "stale");
  const radiation = findSensor(data?.status, "urine_radiation_marker");

  const trendSensor = findSensor(data?.status, trend);
  const trendReadings = chronological(
    (trend === "urine_salinity" ? data?.salinity : data?.ph) ?? [],
  ).filter((r) => r.value !== null);
  // Salinity has no defined unit: plot only readings sharing the newest reading's unit.
  const trendUnit = trendReadings[trendReadings.length - 1]?.unit ?? null;
  const trendSame = trendReadings.filter((r) => r.unit === trendUnit);
  const trendExcluded = trendReadings.length - trendSame.length;
  const trendLabel = TREND_OPTIONS.find((o) => o.key === trend)?.label ?? "";
  const trendRange = trendSensor ? rangeText(trendSensor.config) : null;

  return (
    <div className="screen">
      <ServiceBanner error={error} updatedAt={updatedAt} onRetry={refresh} />
      {!offline && anyStale && lastSample !== null ? (
        <div className="banner banner--stale" role="status">
          <StateIcon state="stale" size={22} />
          <span>
            <strong>Last sample {formatAge(lastSample)}.</strong> Values may have changed:
            take a new sample to get current data.
          </span>
        </div>
      ) : null}
      <div className="orina__grid">
        <div className="orina__cards">
          {URINE_KINDS.map((k, i) => (
            <SensorCard
              key={k}
              title={CARDS[i].title}
              organ={CARDS[i].organ}
              sensor={sensors[i]}
              ageSeconds={liveAge(sensors[i], updatedAt, now)}
              loaded={loaded}
              offline={offline}
              size="sm"
            />
          ))}
        </div>
        <div className="orina__side">
          <Panel
            title="Trend"
            aside={<SegmentedControl label="Series" options={TREND_OPTIONS} value={trend} onChange={setTrend} />}
          >
            <span className="caption">
              {trendLabel}
              {trendUnit ? ` (${unitLabel(trendUnit)})` : ""} · {TREND_DAYS} days · dates in UTC
              {trendExcluded > 0 ? ` · ${trendExcluded} readings in another unit are not shown` : ""}
              {trendRange ? ` · Normal ${trendRange}${trendSensor?.config.provisional ? " · PROV." : ""}` : ""}
            </span>
            <LineChart
              points={trendSame.map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }))}
              start={now - TREND_DAYS * DAY}
              end={now}
              normalMin={trendSensor?.config.normal_min ?? null}
              normalMax={trendSensor?.config.normal_max ?? null}
              showPoints
              width={560}
              height={250}
              label={`${trendLabel}, ${TREND_DAYS} days`}
              emptyText="No readings in 14 days"
            />
          </Panel>
          <RadiationPanel sensor={radiation} ageSeconds={liveAge(radiation, updatedAt, now)} />
        </div>
      </div>
    </div>
  );
}
