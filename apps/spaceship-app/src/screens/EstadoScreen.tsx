import type { ReactNode } from "react";
import type { ReadingStatus, SensorStatus } from "../api/types";
import { getAstronautStatus } from "../api/status";
import { AgeLabel } from "../components/AgeLabel";
import { BodyDiagram } from "../components/BodyDiagram";
import { ErrorNotice } from "../components/ErrorNotice";
import { Panel } from "../components/Panel";
import { StatusBadge } from "../components/StatusBadge";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { SENSOR_LABELS, readingValueText, unitLabel } from "../lib/format";
import { URINE_KINDS, aggregateUrine, findSensor, liveAge, stateBoxClass } from "../lib/sensors";

interface Props {
  astronautId: string;
}

interface CalloutProps {
  title: string;
  status: ReadingStatus | null;
  value: ReactNode;
  unit: string;
  ageSeconds: number | null;
  provisional?: boolean;
  extra?: ReactNode;
}

function Callout({ title, status, value, unit, ageSeconds, provisional, extra }: CalloutProps) {
  const st = status ?? "no_data";
  const noData = st === "no_data";
  return (
    <div className={`callout ${stateBoxClass(st)}`}>
      <div className="callout__title">{title}</div>
      <div className="callout__value">
        <span className="value-lg">{noData ? "---" : value}</span>
        {!noData && unit ? <span className="unit">{unit}</span> : null}
        <AgeLabel seconds={noData ? null : ageSeconds} emphasis={st === "stale"} />
      </div>
      <div className="callout__state">
        {status ? <StatusBadge status={st} /> : <span className="badge">[ … ]</span>}
        {provisional && st !== "no_data" && st !== "no_range" ? (
          <span className="tag">PROV.</span>
        ) : null}
        {extra}
      </div>
    </div>
  );
}

function sensorCallout(
  title: string,
  sensor: SensorStatus | null,
  age: number | null,
  loaded: boolean,
) {
  return (
    <Callout
      title={title}
      status={loaded ? (sensor?.status ?? "no_data") : null}
      value={readingValueText(sensor?.latest)}
      unit={unitLabel(sensor?.latest?.unit)}
      ageSeconds={age}
      provisional={sensor?.config.provisional && sensor.config.normal_min !== null}
    />
  );
}

export function EstadoScreen({ astronautId }: Props) {
  const poll = usePolling(
    `estado:${astronautId}`,
    (signal) => getAstronautStatus(astronautId, signal),
    5000,
  );
  const now = useNow(1000);
  const { data, error, updatedAt } = poll;
  const loaded = data !== null;

  const heart = findSensor(data, "heart_rate");
  const spo2 = findSensor(data, "spo2");
  const muscle = findSensor(data, "muscle_density");
  const urine = URINE_KINDS.map((k) => findSensor(data, k));
  const ph = findSensor(data, "urine_ph");
  const temp = findSensor(data, "urine_temperature");

  const urineStatus = aggregateUrine(urine);
  const urineAges = urine
    .map((s) => liveAge(s, updatedAt, now))
    .filter((a): a is number => a !== null);
  const urineAge = urineAges.length > 0 ? Math.min(...urineAges) : null;
  const missing = urine.filter((s) => s && s.status === "no_data");
  const anyUrine = urineStatus !== "no_data";

  return (
    <div className="screen">
      <ErrorNotice error={error} hasData={loaded} />
      <div className={`estado ${error && loaded ? "dimmed" : ""}`}>
        <BodyDiagram
          lungs={sensorCallout("PULMONES · SpO₂", spo2, liveAge(spo2, updatedAt, now), loaded)}
          heart={sensorCallout("CORAZÓN · PULSO", heart, liveAge(heart, updatedAt, now), loaded)}
          kidneys={
            <Callout
              title="RIÑONES · ORINA"
              status={loaded ? urineStatus : null}
              value={
                <>
                  <span className="value-prefix">pH</span> {readingValueText(ph?.latest)}
                </>
              }
              unit=""
              ageSeconds={urineAge}
              provisional={ph?.config.provisional}
              extra={
                <>
                  {temp?.status === "alert" && temp.config.range_role === "sample_validity" ? (
                    <span className="tag">MUESTRA DUDOSA</span>
                  ) : null}
                  {anyUrine && missing.length > 0 ? (
                    <span className="callout__missing">
                      sin datos: {missing.map((s) => SENSOR_LABELS[s!.kind].replace("ORINA·", "")).join(", ")}
                    </span>
                  ) : null}
                </>
              }
            />
          }
          limbs={sensorCallout(
            "EXTREMIDADES · MÚSCULO",
            muscle,
            liveAge(muscle, updatedAt, now),
            loaded,
          )}
        />
        <Panel title="LEYENDA" className="estado__legend">
          <ul className="legend">
            <li>
              <StatusBadge status="normal" /> dentro del rango
            </li>
            <li>
              <StatusBadge status="alert" /> fuera del rango
            </li>
            <li>
              <StatusBadge status="no_data" /> sin lecturas
            </li>
            <li>
              <StatusBadge status="stale" /> dato viejo, no evaluado
            </li>
            <li>
              <StatusBadge status="no_range" /> sin rango de referencia
            </li>
            <li>
              <span className="tag">PROV.</span> rango provisional
            </li>
          </ul>
          <p className="muted">
            Orina: estado más relevante entre pH, salinidad, color y temperatura. La temperatura solo
            indica si la muestra es válida.
          </p>
          <p className="muted">Refresco cada 5 s.</p>
        </Panel>
      </div>
    </div>
  );
}
