import type { Reading, SensorStatus } from "../api/types";
import { chronological, formatAge, formatNumber, rangeText, unitLabel } from "../lib/format";
import { LineChart } from "./LineChart";
import { StateIcon, StatusPill } from "./StatusPill";

const DAYS = 14;
const DAY = 86_400_000;

interface Props {
  sensor: SensorStatus | null;
  readings: Reading[];
  ageSeconds: number | null;
  now: number;
}

/**
 * Urine radiation marker (8-OHdG from the urine analyser). An indirect marker of oxidative
 * DNA damage, NOT dosimetry: it never states a dose.
 */
export function RadiationPanel({ sensor, readings, ageSeconds, now }: Props) {
  const latest = sensor?.latest ?? null;
  const state = sensor?.status ?? "no_data";
  const config = sensor?.config;
  const range = config ? rangeText(config) : null;
  const points = chronological(readings)
    .filter((r) => r.value !== null)
    .map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }));
  return (
    <section className={`radiation${state === "alert" ? " radiation--flag" : ""}`}>
      <div className="radiation__head">
        <strong>Radiation marker · urinary 8-OHdG</strong>
        <StatusPill state={state} />
      </div>
      <span className="caption">
        {latest?.value != null
          ? `Latest ${formatNumber(latest.value)} ${unitLabel(latest.unit)} · ${formatAge(ageSeconds)}`
          : "No sample yet"}
        {range ? ` · Normal ${range}${config?.provisional ? " · PROV." : ""}` : " · No range"}
        {config?.range_source ? ` · ${config.range_source}` : ""}
      </span>
      <LineChart
        points={points}
        start={now - DAYS * DAY}
        end={now}
        normalMin={config?.normal_min ?? null}
        normalMax={config?.normal_max ?? null}
        status={state}
        showPoints
        width={560}
        height={200}
        label={`Urinary 8-OHdG, ${DAYS} days`}
        emptyText="No readings in 14 days"
      />
      <div className="radiation__warning">
        <StateIcon state="doubtful" size={18} />
        <span>
          It is an <strong>indirect indicator</strong> of oxidative DNA damage, not dosimetry: it
          does not measure dose. Smoking and stress also raise it. For reference, ISS crew dose
          is 0.2 – 0.5 mSv/day (NASA).
        </span>
      </div>
    </section>
  );
}
