import { useState } from "react";
import { SENSOR_KINDS, type SensorKind } from "../api/types";
import { listReadings } from "../api/readings";
import { ErrorNotice } from "../components/ErrorNotice";
import { ReadingsTable } from "../components/ReadingsTable";
import { usePolling } from "../hooks/usePolling";
import { SENSOR_LABELS, formatUtcDateTime } from "../lib/format";

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
    <div className="screen">
      <div className="toolbar">
        <label className="field">
          <span>SENSOR:</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as SensorKind | "")}>
            <option value="">TODOS</option>
            {SENSOR_KINDS.map((k) => (
              <option key={k} value={k}>
                {SENSOR_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <span className="muted">
          {LIMIT} más recientes
          {updatedAt ? ` · actualizado ${formatUtcDateTime(new Date(updatedAt).toISOString())} UTC` : ""}
        </span>
        <button type="button" className="btn" onClick={refresh} disabled={loading}>
          {loading ? "[ACTUALIZANDO…]" : "[ACTUALIZAR]"}
        </button>
      </div>
      <ErrorNotice error={error} hasData={loaded} />
      <div className={error && loaded ? "dimmed" : ""}>
        {loaded && data.length === 0 ? (
          <div className="statebox statebox--no_data empty">[-- SIN DATOS ] No hay lecturas registradas.</div>
        ) : null}
        {loaded && data.length > 0 ? <ReadingsTable readings={data} /> : null}
        {!loaded && !error ? <div className="muted">Cargando…</div> : null}
      </div>
    </div>
  );
}
