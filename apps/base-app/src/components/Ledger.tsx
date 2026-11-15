import type { Link } from "../api/types";
import { batchSerial, delaySeconds, type LedgerEntry } from "../lib/board";
import { formatDuration, utcStamp } from "../lib/format";

interface Props {
  ledger: LedgerEntry[];
  link: Link | null;
  offline: boolean;
}

function content(e: LedgerEntry): string {
  if (e.batches === null) return "Último lote antes de abrir la consola";
  const readings = e.readings === 0 ? "sin lecturas (latido)" : `${e.readings} lecturas`;
  return e.batches > 1 ? `${e.batches} lotes · ${readings}` : readings;
}

/** Batches this console has observed through GET /link, newest first. */
export function Ledger({ ledger, link, offline }: Props) {
  if (ledger.length === 0) {
    let text = "Consultando el enlace…";
    if (offline) text = "Sin registro de lotes: el servicio de tierra no responde.";
    else if (link && !link.last_batch_received_at) text = "Aún no ha llegado ningún lote de la nave.";
    return <p className="empty">{text}</p>;
  }
  return (
    <>
      <table className="log">
        <thead>
          <tr>
            <th scope="col">Lote</th>
            <th scope="col">Contenido</th>
            <th scope="col">Enviado (nave)</th>
            <th scope="col">Recibido (tierra)</th>
            <th scope="col">Tránsito</th>
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
        Lotes observados por esta consola desde que se abrió, consultando el enlace cada 2 s. El
        servicio de tierra no guarda una lista de lotes; si llegan varios entre dos consultas se
        agrupan en una fila.
      </p>
    </>
  );
}
