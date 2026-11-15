import type { CrewMember, Link } from "../api/types";
import { Flap } from "../components/Flap";
import { RangeLabel, SensorName } from "../components/labels";
import { Ledger } from "../components/Ledger";
import { LINK_LATE_S, LINK_LOST_S, linkWords, type LedgerEntry, type LinkState } from "../lib/board";
import { formatDuration, utcStamp } from "../lib/format";

interface Props {
  link: Link | null;
  since: number | null;
  state: LinkState;
  crew: CrewMember[] | null;
  ledger: LedgerEntry[];
  offline: boolean;
}

export function Enlace({ link, since, state, crew, ledger, offline }: Props) {
  const configs = crew?.[0]?.sensors.map((s) => s.config) ?? [];
  const none = "Aún no llegó ningún lote";

  return (
    <>
      <h1 className="sr-only">Enlace con la nave</h1>
      <div className="link-grid">
        <dl className="facts">
          <div>
            <dt>Estado</dt>
            <dd className={`link-state link-state--${state}`}>{linkWords(state, since)}</dd>
          </div>
          <div>
            <dt>Nave</dt>
            <dd>{link?.ship_id ?? <span className="muted">{link ? "Sin identificar: " + none.toLowerCase() : "--"}</span>}</dd>
          </div>
          <div>
            <dt>Último lote enviado (reloj de la nave)</dt>
            <dd>{link?.last_batch_sent_at ? utcStamp(link.last_batch_sent_at) : <span className="muted">{none}</span>}</dd>
          </div>
          <div>
            <dt>Último lote recibido (reloj de tierra)</dt>
            <dd>{link?.last_batch_received_at ? utcStamp(link.last_batch_received_at) : <span className="muted">{none}</span>}</dd>
          </div>
          <div>
            <dt>Tiempo desde el último lote</dt>
            <dd>{since === null ? <span className="muted">{none}</span> : formatDuration(since)}</dd>
          </div>
          <div>
            <dt>Lotes recibidos</dt>
            <dd>
              <Flap text={link ? String(link.batches_received) : "--"} tiles width={6} />
            </dd>
          </div>
          <div>
            <dt>Lecturas recibidas</dt>
            <dd>
              <Flap text={link ? String(link.readings_received) : "--"} tiles width={6} />
            </dd>
          </div>
        </dl>

        <div className="explain">
          <h2>Qué es un dato viejo en tierra</h2>
          <p>
            Tierra mide la edad de cada lectura con su propio reloj, desde que se registró en la nave.
            El retraso del enlace cuenta: una lectura que ya era reciente a bordo puede llegar vieja.
            Cuando su edad supera el límite de su sensor se marca en ámbar como dato viejo y no se
            evalúa contra su rango.
          </p>
          <p>
            Enlace retrasado: {LINK_LATE_S} s o más sin lotes. Sin enlace: {LINK_LOST_S} s o más. Si el
            servicio de tierra no responde, todo valor conocido se muestra como dato viejo.
          </p>
          {configs.length > 0 ? (
            <table className="log">
              <thead>
                <tr>
                  <th scope="col">Sensor</th>
                  <th scope="col">Viejo tras</th>
                  <th scope="col">Rango</th>
                  <th scope="col">Fuente del rango</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr key={c.kind}>
                    <td>
                      <SensorName kind={c.kind} />
                    </td>
                    <td className="num">
                      {c.stale_after_seconds === null ? "Nunca" : formatDuration(c.stale_after_seconds)}
                    </td>
                    <td>
                      {c.kind === "urine_radiation_marker" ? (
                        <span className="muted">Indicador indirecto</span>
                      ) : (
                        <RangeLabel config={c} />
                      )}
                    </td>
                    <td>{c.range_source ?? <span className="muted">Sin fuente</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>

      <section className="section" aria-labelledby="link-ledger">
        <h2 id="link-ledger">Lotes recibidos</h2>
        <Ledger ledger={ledger} link={link} offline={offline} />
      </section>
    </>
  );
}
