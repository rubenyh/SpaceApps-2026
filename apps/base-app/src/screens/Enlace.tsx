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
  const none = "No batch has arrived yet";

  return (
    <>
      <h1 className="sr-only">Link with the ship</h1>
      <div className="link-grid">
        <dl className="facts">
          <div>
            <dt>Status</dt>
            <dd className={`link-state link-state--${state}`}>{linkWords(state, since)}</dd>
          </div>
          <div>
            <dt>Ship</dt>
            <dd>{link?.ship_id ?? <span className="muted">{link ? "Unknown: " + none.toLowerCase() : "--"}</span>}</dd>
          </div>
          <div>
            <dt>Last batch sent (ship clock)</dt>
            <dd>{link?.last_batch_sent_at ? utcStamp(link.last_batch_sent_at) : <span className="muted">{none}</span>}</dd>
          </div>
          <div>
            <dt>Last batch received (ground clock)</dt>
            <dd>{link?.last_batch_received_at ? utcStamp(link.last_batch_received_at) : <span className="muted">{none}</span>}</dd>
          </div>
          <div>
            <dt>Time since the last batch</dt>
            <dd>{since === null ? <span className="muted">{none}</span> : formatDuration(since)}</dd>
          </div>
          <div>
            <dt>Batches received</dt>
            <dd>
              <Flap text={link ? String(link.batches_received) : "--"} tiles width={6} />
            </dd>
          </div>
          <div>
            <dt>Readings received</dt>
            <dd>
              <Flap text={link ? String(link.readings_received) : "--"} tiles width={6} />
            </dd>
          </div>
        </dl>

        <div className="explain">
          <h2>What old data means on ground</h2>
          <p>
            Ground measures the age of each reading with its own clock, from when the ship recorded
            it. Link delay counts: a reading that was recent onboard can arrive old. When its age
            passes its sensor's limit it is marked in amber as old data and not checked against its
            range.
          </p>
          <p>
            Batch late: {LINK_LATE_S} s or more without batches. No link: {LINK_LOST_S} s or more. If
            the ground service does not answer, every known value is shown as old data.
          </p>
          {configs.length > 0 ? (
            <table className="log">
              <thead>
                <tr>
                  <th scope="col">Sensor</th>
                  <th scope="col">Old after</th>
                  <th scope="col">Range</th>
                  <th scope="col">Range source</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr key={c.kind}>
                    <td>
                      <SensorName kind={c.kind} />
                    </td>
                    <td className="num">
                      {c.stale_after_seconds === null ? "Never" : formatDuration(c.stale_after_seconds)}
                    </td>
                    <td>
                      <RangeLabel config={c} />
                    </td>
                    <td>{c.range_source ?? <span className="muted">No source</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>

      <section className="section" aria-labelledby="link-ledger">
        <h2 id="link-ledger">Batches received</h2>
        <Ledger ledger={ledger} link={link} offline={offline} />
      </section>
    </>
  );
}
