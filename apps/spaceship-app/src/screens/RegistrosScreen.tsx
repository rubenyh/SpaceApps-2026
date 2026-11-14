import { useState } from "react";
import { SENSOR_KINDS, type SensorKind } from "../api/types";
import { listReadings } from "../api/readings";
import { QualityMark } from "../components/QualityMark";
import { ReadingsTable } from "../components/ReadingsTable";
import { ServiceBanner } from "../components/ServiceBanner";
import { StateIcon } from "../components/StatusPill";
import { usePolling } from "../hooks/usePolling";
import { SENSOR_LABELS } from "../lib/format";

interface Props {
  astronautId: string;
}

const LIMIT = 100;

export function RegistrosScreen({ astronautId }: Props) {
  const [kind, setKind] = useState<SensorKind | "">("");
  const poll = usePolling(
    `registros:${astronautId}:${kind}`,
    (signal) =>
      listReadings({ astronaut_id: astronautId, kind: kind || undefined, limit: LIMIT }, signal),
    30_000,
  );
  const { data, error, loading, updatedAt, refresh } = poll;
  const loaded = data !== null;

  return (
    <div className="screen screen--fill">
      <div className="toolbar">
        <div className="toolbar__group">
          <label className="field">
            <span>Sensor</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as SensorKind | "")}>
              <option value="">Todos los sensores</option>
              {SENSOR_KINDS.map((k) => (
                <option key={k} value={k}>
                  {SENSOR_LABELS[k]}
                </option>
              ))}
            </select>
          </label>
          <span className="caption">
            Las <strong>{LIMIT}</strong> lecturas más recientes, sin procesar
          </span>
        </div>
        <div className="toolbar__group">
          <span className="caption">Calidad:</span>
          <QualityMark quality="good" />
          <QualityMark quality="suspect" />
          <QualityMark quality="bad" />
          <button type="button" className="btn btn--ghost" onClick={refresh} disabled={loading}>
            {loading ? "Actualizando…" : "Actualizar"}
          </button>
        </div>
      </div>
      <ServiceBanner error={error} updatedAt={updatedAt} onRetry={refresh} />
      {loaded && data.length === 0 ? (
        <div className="banner banner--empty" role="status">
          <StateIcon state="no_data" size={22} />
          <span>Aún no hay lecturas de este tripulante.</span>
        </div>
      ) : null}
      {loaded && data.length > 0 ? <ReadingsTable readings={data} /> : null}
      {!loaded && !error ? (
        <div className="banner" role="status">
          Cargando lecturas…
        </div>
      ) : null}
    </div>
  );
}
