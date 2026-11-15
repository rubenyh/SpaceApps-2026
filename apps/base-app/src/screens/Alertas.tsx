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
        <h1 className="sr-only">Alert log</h1>
        <label className="toolbar__label" htmlFor="alert-filter">
          Astronaut
        </label>
        <select id="alert-filter" value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">All crew</option>
          {ids.map((id) => (
            <option key={id} value={id}>
              {nameOf(id)} ({id})
            </option>
          ))}
        </select>
        <span className="toolbar__meta">
          Newest first · last {limit} received on ground
        </span>
      </div>

      <table className="log log--alerts">
        <thead>
          <tr>
            <th scope="col">No.</th>
            <th scope="col">Astronaut</th>
            <th scope="col">Sensor</th>
            <th scope="col">Value</th>
            <th scope="col">Side</th>
            <th scope="col">Range</th>
            <th scope="col">Recorded (ship)</th>
            <th scope="col">Received (ground)</th>
            <th scope="col">Delay</th>
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
                  <Flap text={a.side === "high" ? "High" : "Low"} className="flap--text flap--red" />
                </td>
                <td>{rangeText(a.normal_min, a.normal_max, r.unit) ?? "No range"}</td>
                <td>{utcStamp(r.recorded_at)}</td>
                <td>{utcStamp(r.ground_received_at)}</td>
                <td className="num">{delay === null ? "--" : formatDuration(delay)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {alerts === null && offline ? (
        <p className="empty">No alert log: the ground service is not answering.</p>
      ) : null}
      {alerts !== null && rows.length === 0 ? (
        <div className="empty">
          <p>
            {who
              ? `No alerts for ${nameOf(who)} in the last ${limit}.`
              : "No alerts recorded on ground."}
          </p>
          <p className="hint">
            An alert is recorded when a reading arrives outside its health range. Sample validity
            ranges and the radiation marker never raise alerts.
          </p>
        </div>
      ) : null}
    </>
  );
}
