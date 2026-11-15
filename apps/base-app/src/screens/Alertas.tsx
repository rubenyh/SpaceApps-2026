import { useState } from "react";
import type { Alert, CrewMember } from "../api/types";
import { Flap, FlapSkeleton } from "../components/Flap";
import { SensorName } from "../components/labels";
import { alertSerial, delaySeconds } from "../lib/board";
import { formatDuration, rangeText, readingValueText, utcStamp } from "../lib/format";

interface Props {
  alerts: Alert[] | null;
  limit: number;
  crew: CrewMember[] | null;
  offline: boolean;
}

export function Alertas({ alerts, limit, crew, offline }: Props) {
  const [who, setWho] = useState("");
  const nameOf = (id: string) => crew?.find((m) => m.astronaut_id === id)?.display_name ?? id;
  // The contract has no astronaut filter; filter the newest `limit` alerts here.
  const ids = [...new Set([...(crew ?? []).map((m) => m.astronaut_id), ...(alerts ?? []).map((a) => a.reading.astronaut_id)])];
  const rows = (alerts ?? []).filter((a) => !who || a.reading.astronaut_id === who);

  return (
    <>
      <div className="toolbar">
        <h1 className="sr-only">Registro de alertas</h1>
        <label className="toolbar__label" htmlFor="alert-filter">
          Astronauta
        </label>
        <select id="alert-filter" value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">Toda la tripulación</option>
          {ids.map((id) => (
            <option key={id} value={id}>
              {nameOf(id)} ({id})
            </option>
          ))}
        </select>
        <span className="toolbar__meta">
          Más recientes primero · últimas {limit} recibidas en tierra
        </span>
      </div>

      <table className="log log--alerts">
        <thead>
          <tr>
            <th scope="col">Nº</th>
            <th scope="col">Astronauta</th>
            <th scope="col">Sensor</th>
            <th scope="col">Valor</th>
            <th scope="col">Lado</th>
            <th scope="col">Rango</th>
            <th scope="col">Registrado (nave)</th>
            <th scope="col">Recibido (tierra)</th>
            <th scope="col">Retraso</th>
          </tr>
        </thead>
        <tbody>
          {alerts === null && !offline
            ? [0, 1, 2].map((i) => (
                <tr key={i} aria-hidden="true">
                  <td colSpan={9}>
                    <FlapSkeleton tiles={12} />
                  </td>
                </tr>
              ))
            : null}
          {rows.map((a) => {
            const r = a.reading;
            const delay = delaySeconds(r.recorded_at, r.ground_received_at);
            return (
              <tr key={r.id}>
                <td>
                  <Flap text={alertSerial(r.id)} tiles className="flap--text" />
                </td>
                <td>{nameOf(r.astronaut_id)}</td>
                <td>
                  <SensorName kind={r.kind} />
                </td>
                <td className="num">
                  {readingValueText(r)} {r.unit}
                </td>
                <td>
                  <Flap text={a.side === "high" ? "Alto" : "Bajo"} className="flap--text flap--red" />
                </td>
                <td>{rangeText(a.normal_min, a.normal_max, r.unit) ?? "Sin rango"}</td>
                <td>{utcStamp(r.recorded_at)}</td>
                <td>{utcStamp(r.ground_received_at)}</td>
                <td className="num">{delay === null ? "--" : formatDuration(delay)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {alerts === null && offline ? (
        <p className="empty">Sin registro de alertas: el servicio de tierra no responde.</p>
      ) : null}
      {alerts !== null && rows.length === 0 ? (
        <div className="empty">
          <p>
            {who
              ? `No hay alertas de ${nameOf(who)} entre las últimas ${limit}.`
              : "No hay alertas registradas en tierra."}
          </p>
          <p className="hint">
            Una alerta se registra cuando una lectura llega fuera de su rango de salud. Los rangos de
            validez de muestra y el marcador de radiación no generan alertas.
          </p>
        </div>
      ) : null}
    </>
  );
}
