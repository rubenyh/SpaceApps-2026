import { getIncidents } from "../api/ground";
import type { GroundIncident } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { delayLabel, sortIncidents, sortUpdates, UPDATE_LABELS, utcFull } from "../lib/incidents";

const POLL_MS = 5_000;

function Incident({ incident: i }: { incident: GroundIncident }) {
  const rules = i.matched_rules.map((r) => r.rule_id).join(", ");
  return (
    <section className="section" aria-labelledby={`inc-${i.id}`}>
      <h2 id={`inc-${i.id}`}>
        Incident {i.id.slice(0, 8)}
        <span className="tag tag--prov">{i.urgency}</span>
      </h2>
      <dl className="facts">
        <div>
          <dt>Began onboard</dt>
          <dd>{i.began_at ? utcFull(i.began_at) : <span className="muted">Not known yet: the "began" update has not reached ground</span>}</dd>
        </div>
        <div>
          <dt>Astronaut</dt>
          <dd>{i.astronaut_id ?? <span className="muted">Not named</span>}</dd>
        </div>
        <div>
          <dt>Action presented onboard</dt>
          <dd>{i.action ?? <span className="muted">No action recorded</span>}</dd>
        </div>
        <div>
          <dt>Acknowledgment</dt>
          <dd>
            {i.acknowledgments.length === 0 ? (
              <span className="muted">Not acknowledged (as far as ground has received)</span>
            ) : (
              i.acknowledgments.map((a) => (
                <div key={a.acknowledged_by}>
                  Acknowledged onboard by {a.acknowledged_by} at {utcFull(a.acknowledged_at)}
                </div>
              ))
            )}
          </dd>
        </div>
      </dl>
      <p className="hint">
        Protocol {i.protocol_id ?? "--"}
        {i.protocol_version ? ` v${i.protocol_version}` : ""} · Matched rules {rules || "--"} · Ship {i.ship_id} · ID {i.id}
      </p>
      <table className="log">
        <thead>
          <tr>
            <th scope="col">Update</th>
            <th scope="col">Onboard time</th>
            <th scope="col">Received on ground</th>
            <th scope="col">Delay</th>
          </tr>
        </thead>
        <tbody>
          {sortUpdates(i.updates).map((u) => (
            <tr key={u.id}>
              <td>
                {UPDATE_LABELS[u.type] ?? u.type}
                {u.acknowledged_by ? ` by ${u.acknowledged_by}` : ""}
              </td>
              <td>{utcFull(u.occurred_at)}</td>
              <td>{utcFull(u.received_at)}</td>
              <td>{delayLabel(u.occurred_at, u.received_at) || <span className="muted">normal transit</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** Read-only incident timeline as stored by ground-api. */
export function Incidents() {
  const { data, error } = usePolling("incidents", getIncidents, POLL_MS);
  const incidents = data ? sortIncidents(data) : null;

  return (
    <>
      <h1 className="sr-only">Incidents</h1>
      <p className="hint">
        Read-only. "Onboard time" is when the event happened on the spaceship (ship clock).
        "Received on ground" is when this ground service stored it (ground clock). A long delay
        means the update waited onboard, for example during a link outage. Newest incident first.
      </p>
      {error ? (
        <p className="empty" role="alert">
          {error.kind === "network" ? "Ground service unreachable." : `Ground service error (${error.message}).`}{" "}
          {incidents ? "Showing the last incidents received; retrying automatically." : "Retrying automatically."}
        </p>
      ) : null}
      {incidents === null && !error ? <p className="empty">Loading incidents…</p> : null}
      {incidents?.length === 0 ? <p className="empty">No incidents have reached ground.</p> : null}
      {incidents?.map((i) => <Incident key={`${i.ship_id}|${i.id}`} incident={i} />)}
    </>
  );
}
