import type { Link } from "../api/types";
import { batchSerial, delaySeconds, type LedgerEntry } from "../lib/board";
import { formatDuration, utcStamp } from "../lib/format";

interface Props {
  ledger: LedgerEntry[];
  link: Link | null;
  offline: boolean;
}

function content(e: LedgerEntry): string {
  if (e.batches === null) return "Last batch before this console opened";
  const readings = e.readings === 0 ? "no readings (heartbeat)" : `${e.readings} readings`;
  return e.batches > 1 ? `${e.batches} batches · ${readings}` : readings;
}

/** Batches this console has observed through GET /link, newest first. */
export function Ledger({ ledger, link, offline }: Props) {
  if (ledger.length === 0) {
    let text = "Checking the link…";
    if (offline) text = "No batch log: the ground service is not answering.";
    else if (link && !link.last_batch_received_at) text = "No batch has arrived from the ship yet.";
    return <p className="empty">{text}</p>;
  }
  return (
    <>
      <table className="log">
        <thead>
          <tr>
            <th scope="col">Batch</th>
            <th scope="col">Content</th>
            <th scope="col">Sent (ship)</th>
            <th scope="col">Received (ground)</th>
            <th scope="col">Transit</th>
          </tr>
        </thead>
        <tbody>
          {ledger.map((e) => {
            const transit = e.sentAt ? delaySeconds(e.sentAt, e.receivedAt) : null;
            return (
              <tr key={e.receivedAt}>
                <td className="serial">{batchSerial(e.batch)}</td>
                <td>{content(e)}</td>
                <td>{utcStamp(e.sentAt)}</td>
                <td>{utcStamp(e.receivedAt)}</td>
                <td>{transit === null ? "--" : formatDuration(transit)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="hint">
        Batches seen by this console since it opened, checking the link every 2 s. The ground
        service keeps no batch list; several batches that arrive between two checks share one
        row.
      </p>
    </>
  );
}
